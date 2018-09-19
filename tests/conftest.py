import flask
import ldap
import pytest
from flask_python_ldap import LDAP

LDAP_BINDDN = 'cn=admin,dc=planetexpress,dc=com'
LDAP_SECRET = 'GoodNewsEveryone'


def is_ldap_up(host, port):
    """Check if the OpenLDAP container is up."""
    conn = ldap.initialize(f'ldap://{host}:{port}')
    conn.simple_bind_s(LDAP_BINDDN, LDAP_SECRET)

    # The OpenLDAP server is pretty quick to start up but it can still be building the indices
    # or computing the memberOf property. So check and wait until that's done before we let the
    # tests proceed, otherwise we get all kinds of crazy errors.
    # conn.search returns either True or False, depending on if the query succeeded or not. As
    # long as the query doesn't succeed we're still starting up.
    res = conn.search_s('dc=planetexpress,dc=com', ldap.SCOPE_BASE, '(objectclass=*)')
    return res


@pytest.fixture(scope='session')
def openldap(docker_ip, docker_services):
    """The OpenLDAP container to test against."""
    host, port = docker_ip, docker_services.port_for('openldap', 389)
    docker_services.wait_until_responsive(
        timeout=600, pause=10,
        check=lambda: is_ldap_up(host, port))

    global LDAP_HOST
    global LDAP_PORT

    LDAP_HOST = host
    LDAP_PORT = port

    return None

@pytest.yield_fixture(scope='session')
def app(openldap):
    """An application for the tests."""
    _app = flask.Flask(__name__)
    _app.config['LDAP_URI'] = f'ldap://{LDAP_HOST}:{LDAP_PORT}'
    _app.config['LDAP_BINDDN'] = LDAP_BINDDN
    _app.config['LDAP_SECRET'] = LDAP_SECRET
    LDAP(_app)
    ctx = _app.test_request_context()
    ctx.push()

    yield _app
