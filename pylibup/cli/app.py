from pathlib import Path
from pylibup.client import PylibClient, Github
from pylibup.cli.base import *
from pylibup.serializers import Yaml
from pylibup.utils import to_path, get_parent_path, exec_shell
from typing import List
import typer

repoCli = createCli(name = 'repo')
stateCli = createCli(name = 'state')

def get_cwd(*paths, posix: bool = True):
    if not paths:
        if posix: return Path.cwd().as_posix()
        return Path.cwd()
    if posix: return Path.cwd().joinpath(*paths).as_posix()
    return Path.cwd().joinpath(*paths)

statefile = get_cwd('.pylibstate.yaml', posix=False)
globalstate_dir = get_parent_path(__file__).joinpath('.pylibstate')
globalstate_dir.mkdir(exist_ok=True)
globalstatefile = globalstate_dir.joinpath('state.yaml')
globalstate_ignore_keys = {'name', 'commit_msg', 'project_name', 'project_dir'}

def load_global_state():
    if globalstatefile.exists(): return Yaml.loads(globalstatefile.read_text())
    return {}

def load_state():
    if statefile.exists(): return Yaml.loads(statefile.read_text())
    return {}

def load_merged_states():
    # global first, local overrides
    globaldata = load_global_state()
    localdata = load_state()
    if localdata: globaldata.update(localdata)
    return globaldata

def save_global_state(overwrite_state: bool = False, **kwargs):
    if globalstatefile.exists():
        data = load_global_state()
        if overwrite_state:
            data.update({k:v for k,v in kwargs.items() if v})
            kwargs = data
        else:
            kwargs.update({k:v for k,v in data.items() if v})
    kwargs = {k:v for k,v in kwargs.items() if k not in globalstate_ignore_keys and v is not None}
    globalstatefile.write_text(Yaml.dumps(kwargs))

def save_state(overwrite_state: bool = False, **kwargs):
    if statefile.exists():
        data = load_state()
        if overwrite_state:
            data.update({k:v for k,v in kwargs.items() if v})
            kwargs = data
        else:
            kwargs.update({k:v for k,v in data.items() if v})
    statefile.write_text(Yaml.dumps(kwargs))


@repoCli.command('init')
def init_new_repo(
    name: Optional[str] = Argument(None),
    project_dir: Optional[str] = Argument(get_cwd()),
    repo_user: Optional[str] = Argument(None),
    github_token: Optional[str] = Option("", envvar="GITHUB_TOKEN"),
    private: bool = Option(True, "--public"),
    overwrite: bool = Option(False),
    overwrite_state: bool = Option(False),
    ):
    state = load_merged_states()
    github_token = github_token or state.get('github_token', '')
    client = PylibClient(github_token = github_token)
    try:
        client.init(project_dir = project_dir, name = name, repo_user = repo_user, private = private, overwrite = overwrite)
        save_state(name = name, project_dir = project_dir, repo_user = repo_user, github_token = github_token, private = private, overwrite = overwrite, overwrite_state = overwrite_state)
    except Exception as e:
        logger.error(e)

@repoCli.command('build')
def build_new_repo(
    config_file: Optional[str] = Argument(get_cwd('metadata.yaml')),
    name: Optional[str] = Argument(None),
    project_dir: Optional[str] = Argument(get_cwd()),
    github_token: Optional[str] = Option("", envvar="GITHUB_TOKEN"),
    pypirc_path: Optional[str] = Option("~/.pypirc", envvar="PYPIRC_PATH"),
    commit_msg: Optional[str] = Option("Initialize"),
    auto_publish: bool = Option(False),
    overwrite: bool = Option(False),
    overwrite_state: bool = Option(False),
    ):
    state = load_merged_states()
    github_token = github_token or state.get('github_token', '')
    pypirc_path = state.get('pypirc_path', pypirc_path)
    config_file = config_file or state.get('config_file')
    project_dir = project_dir or state.get('project_dir')
    client = PylibClient(github_token = github_token, pyirc_path = pypirc_path)
    try:
        client.build(config_file = config_file, project_name = name, project_dir = project_dir, commit_msg = commit_msg, auto_publish = auto_publish, overwrite = overwrite)
        save_state(github_token = github_token, pyirc_path = pypirc_path, config_file = config_file, project_name = name, project_dir = project_dir, commit_msg = commit_msg, auto_publish = auto_publish, overwrite = overwrite, overwrite_state = overwrite_state)
    except Exception as e:
        logger.error(e)


@repoCli.command('cleanup')
def cleanup_repo(
    force: bool = Option(False),
    keep_dir: bool = Option(True),
    ):
    state = load_merged_states()
    project_dir = state.get('project_dir', get_cwd())
    logger.info(f'Planning to remove everything in {project_dir}')
    if not force: force = typer.confirm("Are you sure you want to delete everything in this repo? There is no going back.", abort=True)
    if keep_dir:
        logger.info(f'Removing all files in {project_dir}/*')
        exec_shell(f'rm -rf {project_dir}/*')
    else:
        logger.info(f'Removing directory {project_dir}')
        exec_shell(f'rm -rf {project_dir}')


@repoCli.command('publish')
def publish_new_repo(
    config_file: Optional[str] = Argument(get_cwd('metadata.yaml')),
    github_token: Optional[str] = Option("", envvar="GITHUB_TOKEN"), 
    pypirc_path: Optional[str] = Option("~/.pypirc", envvar="PYPIRC_PATH"),
    commit_msg: Optional[str] = Option("Initialize"),
    overwrite_state: bool = Option(False),
    ):
    state = load_merged_states()
    github_token = github_token or state.get('github_token', '')
    pypirc_path = state.get('pypirc_path', pypirc_path)
    config_file = config_file or state.get('config_file')
    project_dir = state.get('project_dir')
    project_name = state.get('project_name')
    client = PylibClient(github_token = github_token, pyirc_path = pypirc_path)
    try:
        client.publish(commit_msg= commit_msg, config_file = config_file, project_dir = project_dir, project_name = project_name)
        save_state(github_token = github_token, pyirc_path = pypirc_path, config_file = config_file, project_name = project_name, project_dir = project_dir, commit_msg = commit_msg, overwrite_state = overwrite_state)
    except Exception as e:
        logger.error(e)

@repoCli.command('push')
def push_to_repo(
    commit: Optional[str] = Argument("Updating"),
    branch: Optional[str] = Option("main"),
    add_files: bool = Option(True, '--no-add'),
    reinstall: bool = Option(False),
    ):
    cmd = f'cd {get_cwd()} && '
    if add_files: cmd += 'git add . && '
    cmd += f'git commit -m "{commit}" && git push -u origin {branch}'
    if reinstall: cmd += ' && pip install .'
    exec_shell(cmd)

@repoCli.command('reload', short_help = "Does a reinstall via pip install . within the cwd")
def reload_pip_repo():
    cmd = f'cd {get_cwd()} && pip install .'
    exec_shell(cmd)


@repoCli.command('release')
def publish_release(
    tag: Optional[str] = Option("v0.0.1"),
    tag_message: Optional[str] = Option("Stable Release"),
    release_name: Optional[str] = Option("Release v0.0.1"),
    release_message: Optional[str] = Option("Stable Release"),
    draft: bool = Option(False),
    prerelease: bool = Option(False),
    branch: Optional[str] = Option("main"),
    push_first: bool = Option(True, '--no-push'),
    github_token: Optional[str] = Option("", envvar="GITHUB_TOKEN")
    ):
    state = load_merged_states()
    repo_name = state.get('repo')
    if not repo_name:
        logger.error('Unable to locate repo name in state.')
        return
    if push_first:
        exec_shell(f'cd {get_cwd()} && git add . && git commit -m "{release_message}" && git push -u origin {branch}')
    github_token = github_token or state.get('github_token', '')
    github = Github(login_or_token=github_token)
    repo = github.get_repo(repo_name)
    rez = repo.create_git_tag_and_release(tag = tag, tag_message = tag_message, release_name= release_name, release_message= release_message, draft = draft, prerelease = prerelease)
    logger(f'Created Release: {release_name}')
    logger(rez)

    

@repoCli.command('meta')
def display_meta(
    config_file: Optional[str] = Argument(get_cwd('metadata.yaml')),
    ):
    state = load_state()
    config_file = config_file or state.get('config_file')
    config_path = to_path(config_file)
    if not config_path.exists():
        logger.error(f'{config_file} does not exist')
        return
    config_data = '\n' + config_path.read_text()
    logger(config_data)


@stateCli.command('local')
def display_state():
    state = load_state()
    logger(state)


@stateCli.command('global')
def display_globalstate():
    state = load_global_state()
    logger(state)


@stateCli.command('merged')
def display_merged_state():
    state = load_merged_states()
    logger(state)

@stateCli.command('pypi')
def display_pypi_state():
    from pylibup.config import load_pypi_creds
    state = load_merged_states()
    creds = load_pypi_creds(state.get('pypirc_path', '~/.pypirc'))
    logger(creds)


@stateCli.command('set')
def set_state(
        states: List[str],
        global_state: bool = Option(False),
        overwrite_state: bool = Option(True),
    ):
    statevals = load_merged_states()
    for state in states:
        s = state.split('=', 1)
        key, val = s[0].strip(), s[1].strip()
        if val:
            logger.info(f'Setting {key} -> {val}. Previous: {statevals.get(key)}')
            statevals[key] = val
    if global_state:
        logger.info(f'Saving Global State: {globalstatefile.as_posix()}')
        save_global_state(overwrite_state = overwrite_state, **statevals)
    else:
        logger.info(f'Saving Local State: {statefile.as_posix()}')
        save_state(overwrite_state = overwrite_state, **statevals)