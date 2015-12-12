import json

from fabric.api import *
from fabric.contrib.files import exists, upload_template
from fabric.operations import sudo

# ~$ CONFIGURATIONS
# ---------------------------------------------------------------------

APP = {
    "url"     : "revelsix.com",
    "name"    : "revelsix_app",
    "user"    : "revelsix_user",
    "password": "mierd4123",
    "group"   : "revelsix_team",
    "path"    : "/var/www",
    "deps": [  # System's Packages dependencies
        "php5-fpm",
        "php5-cli",
        "nginx",
        "git",
    ],
    "local_deps": [],
}


# Path configurations.
CONFIG_DIR = './config'  # Locally
NGINX_DIR = '/etc/nginx' # Remote

PROJECT_PATH = "%s/%s" % (APP["path"], APP["url"]) # /var/www/app_url
PROJECT_GIT_PATH = "%s.git" % PROJECT_PATH # /var/www/app_url.git
LOG_PATH = "%s/var/log" % PROJECT_PATH # /var/www/app_url/var/log
USER_HOME = "%s/%s" % ("/webapps", APP["user"]) # /webapps/user


SERVERS = {
    "production": {
        "domain": "54.86.232.209",
        "ssh_port": "22",
        "branch": "master",
        },

    "develop": {
        "domain": "localhost",
        "ssh_port": "22",
        "branch": "master",
        },
    "test": {
        "domain": "104.236.57.9",
        "ssh_port": "22",
        "branch": "master",
        },
    }


# ~$ UTILS
# ---------------------------------------------------------------------

class SuperUser(object):

    @staticmethod
    def username():
        """
        Get superuser username from config/credentials.json.
        """
        with open('%s/credentials.json'%CONFIG_DIR) as data_file:
            try:
                data = json.load(data_file)
                return data["username"]
            except Exception, e:
                raise Exception('Yo need a credentials.json file')

    @staticmethod
    def password():
        """
        Get superuser password from config/credentials.json.
        """
        with open('%s/credentials.json'%CONFIG_DIR) as data_file:
            try:
                data = json.load(data_file)
                return data["password"]
            except Exception, e:
                raise Exception('Yo need a credentials.json file')


class Utils(object):
    @staticmethod
    def upload_key():
        """
        Upload  id_rsa.pub file to server.
        This file is obtained from ssh-keygen command.
        """
        try:
            local("ssh-copy-id %s@%s"%(APP["user"], env.hosts[0]))
        except Exception, e:###
            raise Exception('Unfulfilled local requirements')


def set_stage(stage_name='develop'):
    if stage_name in SERVERS.keys():
        env.stage = stage_name
        env.hosts = [SERVERS[env.stage]["domain"], ]
        env.branch = SERVERS[env.stage]["branch"]

    else:
        print_servers()


def set_user(superuser=False):
    if superuser:
        env.user = SuperUser.username()
        env.password = SuperUser.password()
    else:
        env.user = APP["user"]
        env.password = APP["password"]


# ~$ CONFIGURATIONS
# ---------------------------------------------------------------------

class Server(object):
    @staticmethod
    def upgrade():
        """
        Update and upgrade server.
        """
        sudo('apt-get update -y')
        sudo('apt-get upgrade -y')

    @staticmethod
    def deps():
        """
        Install all server dependencies.
        """
        sudo('apt-get install -y %s' % ' '.join(APP["deps"]))

    @staticmethod
    def restart_services():
        """
        Restart nginx.
        """
        sudo('service nginx restart')

    @staticmethod
    def clean():
        """
        Remove all server dependencies.
        """
        sudo('apt-get remove %s' % ' '.join(APP["deps"]))


class Conf(object):

    @staticmethod
    def user():
        """
         Create app user.
        """
        sudo('adduser %s --home %s --disabled-password --gecos \"\"' % (APP["user"], USER_HOME))

        sudo('echo \"%s:%s\" | sudo chpasswd' % (APP["user"], APP["password"]))
        sudo('mkdir -p %s' % USER_HOME)

    @staticmethod
    def group():
        """
         Create app group.
        """
        sudo('groupadd --system %s'%APP["group"])
        sudo('useradd --system --gid %s \
              --shell /bin/bash --home %s %s'
             % (APP["group"], USER_HOME, APP["user"]))

    @staticmethod
    def path():
        """
         Create app group.
        """
        if exists("/var/www") is False:
            sudo("mkdir -p /var/www")

        if exists(PROJECT_PATH) is False:
            sudo("mkdir -p %s"%PROJECT_PATH)

        if exists("%s/var/log"%PROJECT_PATH) is False:
            sudo("mkdir -p %s/var/log"%PROJECT_PATH)

        sudo('touch %s/nginx-access.log'%LOG_PATH)
        sudo('touch %s/nginx-error.log'%LOG_PATH)


    @staticmethod
    def nginx():
        """
        1. Remove default nginx config file.
        2. Create new config file.
        3. Copy local config to remote config.
        4. Setup new symbolic link.
        """
        if exists('%s/sites-enabled/default'%NGINX_DIR):
            sudo('rm %s/sites-enabled/default'%NGINX_DIR)

        if exists('%s/sites-available/default'%NGINX_DIR):
            sudo('rm %s/sites-available/default'%NGINX_DIR)

        if exists('%s/sites-enabled/%s'%(NGINX_DIR,APP["url"])):
            sudo('rm %s/sites-enabled/%s'%(NGINX_DIR,APP["url"]))

        if exists('%s/sites-available/%s'%(NGINX_DIR,APP["url"])):
            sudo('rm %s/sites-available/%s'%(NGINX_DIR,APP["url"]))

        with lcd(CONFIG_DIR):
            with cd('%s/sites-available/'%NGINX_DIR):
                upload_template(
                    filename="./nginx.conf",
                    destination='%s/sites-available/%s'%(NGINX_DIR,APP["url"]),
                    template_dir="./",
                    context={
                        "project_name": APP["name"],
                        "project_path": PROJECT_PATH,
                        "project_url": APP["url"],
                    },
                    use_sudo=True,
                    )

        sudo('ln -s %s/sites-available/%s \
            %s/sites-enabled/'%(NGINX_DIR,APP["url"],NGINX_DIR))

    @staticmethod
    def git():
        """
        1. Setup bare Git repo.
        2. Create post-receive hook.
        """

        with cd(APP["path"]):
            sudo('mkdir -p %s.git'%APP["url"])
            with cd('%s.git'%APP["url"]):
                sudo('git init --bare')
                with lcd(CONFIG_DIR):
                    with cd('hooks'):
                        upload_template(
                            filename="post-receive",
                            destination=PROJECT_GIT_PATH+"/hooks",
                            template_dir="./",
                            context={
                                "project_path": PROJECT_PATH,
                            },
                            use_sudo=True,
                        )
                        sudo('chmod +x post-receive')

    @staticmethod
    def add_remote():
        """
        1. Delete existent server remote git value.
        2. Add existent server remote git value.
        """
        local('git remote remove %s' % env.stage)
        local('git remote add %s %s@%s:%s.git' % (
            env.stage, APP["user"], env.hosts[0], PROJECT_PATH,
        ))

    @staticmethod
    def fix_permissions():
        """
         Fix Permissions.
        """
        sudo('chown -R %s:%s %s'%(APP["user"], "www-data", PROJECT_PATH))
        sudo('chown -R %s:%s %s.git'%(APP["user"], "www-data", PROJECT_PATH))
        sudo('chmod -R g+w %s'%PROJECT_PATH)
        sudo('chmod -R g+w %s.git'%PROJECT_PATH)


class Project(object):

    @staticmethod
    def push():
        """
        Push changes to selected server.
        """
        local("git push %s %s" % (env.stage, env.branch))

    @staticmethod
    def clean():
        """
        1. kill all user's processes.
        2. Delete app user folder.
        3. Delete project folder.
        """
        sudo('pkill -u %s' % APP["user"])

        if exists(PROJECT_PATH):
            sudo('rm -rf %s' % PROJECT_PATH)
        if exists('%s/sites-enabled/%s' % (NGINX_DIR, APP["url"])):
            sudo('rm -f %s/sites-enabled/%s' % (NGINX_DIR, APP["url"]))
        if exists('%s/sites-available/%s' % (NGINX_DIR, APP["url"])):
            sudo('rm -f %s/sites-available/%s' % (NGINX_DIR, APP["url"]))

        sudo('groupdel %s' % APP["group"])
        sudo('userdel -r %s' % APP["user"])
        sudo("rm -rf %s" % PROJECT_PATH)
        sudo("rm -rf %s.git" % PROJECT_PATH)

# ~$ COMMANDS
# ---------------------------------------------------------------------


@task
def production():
    """
    Set stage as production.
    """
    set_stage('production')


@task
def develop():
    """
    Set stage as develop.
    """
    set_stage('develop')


@task
def stage():
    """
    Set stage as develop.
    """
    set_stage('stage')


@task
def test():
    """
    Set stage as test.
    """
    set_stage('test')


@task
def restart(*args):
    """
    Restart all app services.
    """
    set_user(superuser=True)
    with settings(warn_only=True):
        execute(Server.restart_services, hosts=env.hosts)

@task()
def deploy(*args):
    """
    Deploy application in selected server(s)
    """
    set_user()
    with settings(warn_only=True):
        execute(Project.push, hosts=env.hosts)

@task
def install(*args):
    """
    Install app in selected server(s)
    """
    set_user(superuser=True)
    with settings(warn_only=True):
        execute(Project.clean, hosts=env.hosts)
        execute(Server.deps, hosts=env.hosts)
        execute(Conf.user, hosts=env.hosts)
        execute(Conf.group, hosts=env.hosts)
        execute(Conf.path, hosts=env.hosts)
        execute(Conf.git, hosts=env.hosts)
        execute(Conf.add_remote, hosts=env.hosts)
        execute(Conf.nginx, hosts=env.hosts)
        execute(Conf.fix_permissions, hosts=env.hosts)

@task
def uninstall(*args):
    """
    Uninstall app in selected server(s)
    """
    set_user(superuser=True)
    with settings(warn_only=True):
        execute(Project.clean, hosts=env.hosts)

@task
def add_remote(*args):
    """
    Add project repo url to local git configuration.
    """
    with settings(warn_only=True):
        execute(Conf.add_remote, hosts=env.hosts)

@task
def upload_key(*args):
    """
    Upload SSH key to server.
    """
    set_user(superuser=True)
    with settings(warn_only=True):
        execute(Utils.upload_key, hosts=env.hosts)


@task
def help():
    print ""
    print "~$ COMMANDS"
    print "-------------------------------------------------------------------------"
    print ""
    print "  - [server] install            Install project into server."
    print "  - [server] uninstall          Remove project from server."
    print "  - [server] deploy             Deploy project to server."
    print "  - [server] restart            Restart project services."
    print "  - [server] upload_key         Upload SSH key to server."
    print "  - [server] add_remote         Add git remote from server to local git config."
    print ""
    print "-------------------------------------------------------------------------"


@task
def print_servers():
    print ""
    print "~$ SERVERS"
    print "---------------------------------------------------------------------"
    print ""
    for server in SERVERS.keys():
        print "   - "+server
    print ""
    print "---------------------------------------------------------------------"
    print ""