import requests
from git import Repo
from github import Github
from jinja2 import Template

from .envs import envToStr
from .types import *
from .utils import get_logger, to_path, Path, exec_shell
from .serializers import Yaml, Json, Base
from .static import *


logger = get_logger()

class BaseCls(BaseModel):
    class Config:
        arbitrary_types_allowed = True
    
    def get(self, name, default: Any = None):
        return getattr(self, name, default)


class PylibStructure(BaseCls):
    modules: Optional[List[str]] = []

class PylibDockerBuildOptions(BaseCls):
    app_name: Optional[str]
    require_ecr: Optional[bool] = False
    ecr_options: Optional[Dict[str, Any]] = {}
    docker_options: Optional[Dict[str, Any]] = {}

class PylibGithubWorkflows(BaseCls):
    pypi_publish: Optional[bool] = True
    docker_build: Optional[bool] = False
    docker_build_options: Optional[PylibDockerBuildOptions] = Field(default=PylibDockerBuildOptions)
    

class PylibOptions(BaseCls):
    default_branch: Optional[str] = 'main'
    include_init: Optional[bool] = True
    include_app: Optional[bool] = False
    include_dockerfile: Optional[bool] = False
    include_buildscript: Optional[bool] = True
    include_reqtext: Optional[bool] = True
    private: Optional[bool] = True


class PylibConfigData(BaseCls):
    setup: Optional[Dict[str, Any]]
    repo: Optional[str]
    readme_text: Optional[str]
    project_description: Optional[str]
    gitignores: Optional[List[str]]
    structure: Optional[PylibStructure]
    secrets: Optional[Dict[str, Any]]
    options: Optional[PylibOptions] = Field(default = PylibOptions)
    workflows: Optional[PylibGithubWorkflows] = Field(default = PylibGithubWorkflows)

    @property
    def opt(self) -> PylibOptions: return self.options
    
    @property
    def wkflw(self) -> PylibGithubWorkflows: return self.workflows
    
    @property
    def libname(self) -> str:
        if self.setup.get('lib_name'): return self.setup['lib_name']
        if self.setup.get('pkg_name'): return self.setup['pkg_name']
        return self.repo_name or ''


    @property
    def description(self):
        if self.project_description: return self.project_description
        if self.setup.get('description'): return self.setup['description']
        return None

    @property
    def user_repo(self):
        if self.repo: return self.repo.split('/', 1)[0].strip()
        if self.setup and self.setup.get('git_repo'): return self.setup['git_repo']
        return None
    
    @property
    def repo_name(self):
        if self.repo: return self.repo.split('/', 1)[-1].strip()
        if self.setup: 
            if self.setup.get('pkg_name'): return self.setup['pkg_name']
            if self.setup.get('lib_name'): return self.setup['lib_name']
        return None

    @property
    def repo_path(self):
        if not self.user_repo and not self.repo_name: return None
        return f'{self.user_repo}/{self.repo_name}'
    
    @property
    def repo_url(self):
        return f'https://github.com/{self.repo_path}.git'
    
    @property
    def tmpl_setup_py(self):
        if not self.setup: return None
        tmpl = Template(setup_py_template)
        return tmpl.render(self.setup)
    
    @property
    def tmpl_requirements_txt(self):
        if not self.opt.include_reqtext: return None
        tmpl = Template(install_requirements_template)
        return tmpl.render(self.setup)

    @property
    def tmpl_readme_md(self):
        # if not self.readme_text: return None
        tmpl = Template(readme_template)
        readme_data = self.setup or {}
        readme_data['readme_text'] = self.readme_text
        return tmpl.render(readme_data)
    
    @property
    def tmpl_gitignore(self):
        if not self.gitignores: return None
        tmpl = Template(gitignores_template)
        data = {'gitignore': self.gitignores}
        return tmpl.render(data)
    
    @property
    def tmpl_workflows_enabled(self):
        return bool(self.wkflw.docker_build or self.wkflw.pypi_publish)

    @property
    def tmpl_github_action_pypi_publish(self):
        if not self.wkflw.pypi_publish: return None
        return github_action_template_pypi_publish    
    
    @property
    def tmpl_github_action_docker_build(self):
        if not self.wkflw.docker_build: return None
        tmpl = Template(github_action_template_docker_build)
        data = {
            'app_name': self.wkflw.docker_build_options.app_name or self.setup.get('lib_name', self.setup.get('pkg_name')), 
            'require_ecr': self.wkflw.docker_build_options.require_ecr,
            'ecr_options': self.wkflw.docker_build_options.ecr_options,
            'docker_options': self.wkflw.docker_build_options.docker_options,
        }
        return tmpl.render(data)

    @property
    def tmpl_build_sh(self):
        if not self.opt.include_buildscript: return None
        return build_sh_template
    
    @property
    def tmpl_init_py(self):
        if not self.opt.include_init: return None
        tmpl = Template(pyinit_template)
        data = {'modules': self.structure.modules}
        return tmpl.render(data)
    
    @property
    def tmpl_dockerfile_app(self):
        if not self.opt.include_app and not self.opt.include_dockerfile: return None
        return dockerfile_fastapi_template
    
    @property
    def needs_ipyirc(self):
        return self.wkflw.pypi_publish
    
    def should_add_to_commit(self, filename: str):
        return not any(i in filename or filename in i for i in self.gitignores)

    def get_secrets(self):
        data = {}
        for key, val in self.secrets:
            if val:
                if isinstance(val, str): data[key] = val
                if isinstance(val, dict) and val.get('from'):
                    data[key] = envToStr(val['from'], envToStr(key))
            else: data[key] = envToStr(envToStr(key))
        return data


class PylibConfig:
    def __init__(self, github: Github, github_token: str, config_file: str, project_name: str, project_dir: str = None, *args, **kwargs):
        self.github = github
        self.github_token = github_token
        self.config_file = config_file
        self.repo_files = []
        self.set_working_project(project_name, project_dir)
        self.configfile_data = self.load_config_file(self.config_file)
        self.config = self.load_config_data(self.configfile_data)
        self.setup_repo()

    def setup_repo(self):
        if not self.working_dir.joinpath('.git').exists(): self.repo = Repo.init(self.working_dir, bare=False, initial_branch=self.config.opt.default_branch)
        else: self.repo = Repo(self.working_dir, search_parent_directories=True)

    def set_working_project(self, project_name: str = None, project_dir: str = None):
        self.current_dir = to_path(project_dir) if project_dir else Path.cwd()
        if not project_name: project_name = self.current_dir.stem
        self.working_dir = self.current_dir.joinpath(project_name) if project_name not in self.current_dir.as_posix() else self.current_dir
        self.project_name = project_name
        if not self.working_dir.exists():
            self.working_dir.mkdir(parents=True)
        self.workflow_dir = self.working_dir.joinpath('.github/workflows')
        self.app_dir = self.working_dir.joinpath('app')
        if not self.config_file:
            if self.working_dir.joinpath('metadata.yaml').exists():
                self.config_file = self.working_dir.joinpath('metadata.yaml')
            elif self.current_dir.joinpath('metadata.yaml').exists():
                self.config_file = self.current_dir.joinpath('metadata.yaml')
            assert self.config_file, 'No specified config file'

    @classmethod
    def load_config_file(cls, config_file: str):
        config_file = to_path(config_file)
        if config_file.suffix == '.json': loader = Json.loads
        elif config_file.suffix == '.yaml': loader = Yaml.loads
        return loader(config_file.read_text())
    
    @classmethod
    def load_config_data(cls, config_data: Dict[str, Any]) -> PylibConfigData:
        return PylibConfigData(**config_data)
    
    @property
    def github_username(self) -> str:
        return self.github.get_user().login
    
    @property
    def github_repo_user(self) -> str:
        if self.config.user_repo: return self.config.user_repo
        return self.github_username

    @property
    def github_repo_name(self) -> str:
        if self.config.repo_name: return self.config.repo_name
        return self.project_name

    @property
    def github_repo_path(self):
        if self.config.repo_path: return self.config.repo_path
        return f'{self.github_repo_user}/{self.github_repo_name}'
    
    @property
    def user_authentication(self):
        return Base.b64_encode(f'{self.github_username}:{self.github_token}')

    @property
    def github_headers(self):
        return {'Accept': 'application/json, application/vnd.github.v3+json', 'Content-Type': 'application/json', 'Authorization': f'Basic {self.user_authentication}'}

    def get_github_repo(self):
        return requests.get(f'https://api.github.com/repos/{self.github_repo_path}', headers=self.github_headers)

    def create_github_repo(self, **kwargs):
        if self.repo_exists: return
        data = { 
            'name': self.github_repo_name,
            'private': self.config.opt.private,
            'description': self.config.description,
            'default_branch': self.config.opt.default_branch,
        }
        if kwargs: data.update(kwargs)
        return requests.post(url = 'https://api.github.com/user/repos', headers=self.github_headers, json=data)

    @property
    def repo_exists(self) -> bool:
        return bool(self.get_github_repo().status_code < 399)
    
    def publish_repo(self):
        if not self.repo_exists:
            self.create_github_repo()
            exec_shell(f'cd {self.working_dir} && git remote add origin {self.config.repo_url} && git branch -M {self.config.opt.default_branch}')
        exec_shell(f'cd {self.working_dir} && git push -u origin {self.config.opt.default_branch}')


    def build_tmpl(self, tmpl_data: Union[str, Any], filename: str, overwrite: bool = False, add_to_commit: bool = True):
        if tmpl_data:
            tmpl_file = self.working_dir.joinpath(filename)
            if tmpl_file.exists() and not overwrite: pass
            logger(f'Building: {filename}')
            tmpl_file.write_text(tmpl_data)
            if add_to_commit:
                self.repo_files.append(tmpl_file.as_posix())

    def build_base(self, overwrite: bool = False, *args, **kwargs):
        self.build_tmpl(tmpl_data = self.config.tmpl_setup_py,  filename = 'setup.py',  overwrite=overwrite)
        self.build_tmpl(tmpl_data = self.config.tmpl_build_sh,  filename = 'build.sh',  overwrite=overwrite, add_to_commit = self.config.should_add_to_commit('build.sh'))
        self.build_tmpl(tmpl_data = self.config.tmpl_requirements_txt,  filename = 'requirements.txt', overwrite=overwrite)
        self.build_tmpl(tmpl_data = self.config.tmpl_readme_md,  filename = 'README.md',  overwrite=overwrite)
        self.build_tmpl(tmpl_data = self.config.tmpl_gitignore,  filename = '.gitignore',  overwrite=overwrite)

    def build_pylib_structure(self, overwrite: bool = False, *args, **kwargs):
        if not self.config.structure: return
        logger('Setting up Pylib structure')
        pydir = self.working_dir.joinpath(self.config.libname)
        pydir.mkdir(parents=True, exist_ok=True)
        for module in self.config.structure.modules:
            tmpl_file = pydir.joinpath(f'{module}.py')
            if tmpl_file.exists() and not overwrite: pass
            logger(f'Adding {self.config.libname}/{module}.py')
            tmpl_file.touch(exist_ok=True)
            self.repo_files.append(tmpl_file.as_posix())
        
        if self.config.opt.include_init:
            tmpl_file = pydir.joinpath('__init__.py')
            if tmpl_file.exists() and not overwrite: pass
            tmpl_file.write_text(self.config.tmpl_init_py)
            self.repo_files.append(tmpl_file.as_posix())
    
    def build_github_workflows(self, overwrite: bool = False, *args, **kwargs):
        if not self.config.tmpl_workflows_enabled: return
        logger('Setting up Github Workflows')
        self.workflow_dir.mkdir(parents=True, exist_ok=True)

        if self.config.tmpl_github_action_pypi_publish:
            tmpl_file = self.workflow_dir.joinpath('python-publish.yaml')
            if tmpl_file.exists() and not overwrite: pass
            logger('Building: .github/workflows/python-publish.yaml')
            tmpl_file.write_text(self.config.tmpl_github_action_pypi_publish)
            self.repo_files.append(tmpl_file.as_posix())
        
        if self.config.tmpl_github_action_docker_build:
            tmpl_file = self.workflow_dir.joinpath('docker-build.yaml')
            if tmpl_file.exists() and not overwrite: pass
            logger('Building: .github/workflows/docker-build.yaml')
            tmpl_file.write_text(self.config.tmpl_github_action_docker_build)
            self.repo_files.append(tmpl_file.as_posix())
    
    def build_docker_app(self, overwrite: bool = False, *args, **kwargs):
        if not self.config.opt.include_app: return
        logger('Setting up AppDir')
        self.app_dir.mkdir(parents=True, exist_ok=True)
        for appfile in ['__init__', 'config', 'client', 'classes', 'routez', 'utils']:
            tmpl_file = self.app_dir.joinpath(f'{appfile}.py')
            if tmpl_file.exists() and not overwrite: pass
            logger(f'Adding app/{appfile}.py')
            tmpl_file.touch(exist_ok=True)
            self.repo_files.append(tmpl_file.as_posix())

        if self.config.tmpl_dockerfile_app:
            tmpl_file = self.working_dir.joinpath('Dockerfile')
            if tmpl_file.exists() and not overwrite: pass
            logger('Adding Dockerfile for App')
            tmpl_file.write_text(self.config.tmpl_dockerfile_app)
            self.repo_files.append(tmpl_file.as_posix())

    
    def build(self, commit_msg: str = 'Initialize', overwrite: bool = False, auto_publish: bool = False, *args, **kwargs):
        logger.info('====================================================')
        logger.info(f'Building Repo: {self.project_name} @ {self.config.opt.default_branch}')
        logger.info('====================================================')
        self.build_base(overwrite=overwrite, *args, **kwargs)
        self.build_pylib_structure(overwrite=overwrite, *args, **kwargs)
        self.build_github_workflows(overwrite=overwrite, *args, **kwargs)
        self.build_docker_app(overwrite=overwrite, *args, **kwargs)
        if self.repo_files:
            logger.info(f'Adding {len(self.repo_files)} Files to Git Index')
            self.repo.index.add(self.repo_files)
        logger.info(f'Adding Commit: {commit_msg}')
        self.repo.index.commit(commit_msg)
        if auto_publish:
            logger.info(f'Publishing {self.project_name}')
            self.publish_repo()
        logger('Completed Pylib Build. Have fun!')
    
    def publish_repo(self, commit_msg: str = None):
        if self.repo_exists: logger.warn(f'Repo already exists. Skipping Publishing: {self.project_name}')
        else: logger.info(f'Publishing {self.project_name}')
        if commit_msg: 
            logger.info(f'Adding Commit: {commit_msg}')
            self.repo.index.commit(commit_msg)
        self.publish_repo()


def get_metadata_template(github: Github, name: str, repo_user: str = None, private: bool = True, **kwargs):
    metadata = default_pylib_metadata.copy()
    #if kwargs: metadata.update(kwargs)
    caller = github.get_user()
    if not repo_user: repo_user = caller.login
    metadata['repo'] = f'{repo_user}/{name}'
    #metadata['options']['private'] = private
    metadata['setup'].update({
        'author': caller.name or repo_user,
        'description': kwargs.get('description', kwargs.get('project_description')),
        'email': caller.email,
        'git_repo': f'{repo_user}',
        'pkg_name': name,
        'lib_name': kwargs.get('lib_name', name)
    })
    metadata['project_description'] = kwargs.get('project_description', kwargs.get('description'))
    metadata['readme_text'] = kwargs.get('readme_text', metadata['project_description'])
    if kwargs.get('secrets'):
        metadata['secrets'] = kwargs['secrets']
    #logger.info(metadata)
    return Yaml.dumps(metadata)




    



        


        






