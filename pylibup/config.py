from .envs import *
from .utils import to_path, Path
from .types import *

class PypiCreds(BaseModel):
    name: str
    username: str
    password: str


def load_pypi_creds(path: str = '~/.pypirc'):
    fpath = to_path(Path(path).expanduser())
    if not fpath.exists(): return None
    text = fpath.read_text()
    data = text.split('\n\n')
    rez = {}
    for item in data:
        items = [i.strip() for i in item.split('\n') if i.strip()]
        name = items.pop(0)
        r = {'name': name.replace('[', '').replace(']', '')}
        for i in items:
            d = i.split(' = ')
            r[d[0].strip()] = d[1].strip()
        rez[r['name']] = PypiCreds(**r)
    return rez
    
# We assume user is authenticated to git right?
class GitConfig:
    token: str = envToStr('GITHUB_TOKEN', '')
    


