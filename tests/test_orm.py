"""Tests for the ORM."""
import pytest
import uuid

from flask_python_ldap import Entry, Attribute

LDAP_AUTH_BASEDN = 'ou=people,dc=planetexpress,dc=com'
LDAP_AUTH_ATTR = 'mail'
LDAP_AUTH_SEARCH_FILTER = '(objectClass=inetOrgPerson)'

ENTRY_NAME = 'testuser'
ENTRY_TITLE = 'test-title'


class User(Entry):
    # LDAP meta-data
    base_dn = LDAP_AUTH_BASEDN
    entry_rdn = 'cn'
    object_classes = ['inetOrgPerson']

    # inetOrgPerson
    name = Attribute('cn')
    email = Attribute('mail', is_list=True)
    title = Attribute('title')
    userid = Attribute('uid')
    surname = Attribute('sn')
    givenname = Attribute('givenName')


class Account(User):
    # LDAP meta-data
    object_classes = ['posixAccount']

    # posixAccount
    uidnumber = Attribute('uidNumber')
    gidnumber = Attribute('gidNumber')
    shell = Attribute('loginShell')
    home = Attribute('homeDirectory')
    password = Attribute('userPassword')


def test_attrs():
    class A(Entry):
        a = Attribute('a')
    class B(Entry):
        b = Attribute('b')
    class C(B):
        c = Attribute('c')

    assert 'a' in A._attr_defs.keys()
    assert 'b' not in A._attr_defs.keys()
    assert 'c' not in A._attr_defs.keys()

    assert 'a' not in B._attr_defs.keys()
    assert 'b' in B._attr_defs.keys()
    assert 'c' not in B._attr_defs.keys()

    assert 'a' not in C._attr_defs.keys()
    assert 'b' in C._attr_defs.keys()
    assert 'c' in C._attr_defs.keys()


@pytest.yield_fixture(scope='function')
def entry():
    yield User(name=ENTRY_NAME, title=ENTRY_TITLE)


@pytest.yield_fixture(scope='function')
def test_name():
    yield 'test-' + uuid.uuid4().hex[-6:]


def test_init(entry):
    """Instantiate a model"""
    assert entry.name == ENTRY_NAME
    assert entry.title == ENTRY_TITLE


def test_add(entry):
    try:
        entry.email = 'lol'
    except:
        assert False, 'Should not except'

def test_change(entry):
    NEW_NAME = 'asdf'
    entry.name = NEW_NAME
    assert entry.name == NEW_NAME
    assert entry.title == ENTRY_TITLE

def test_search_change(app):
    res = User.query.filter('(cn=Hubert J. Farnsworth)').first()
    assert 'hubert@planetexpress.com' in res.email

def test_endswith(entry):
    res = User.query.filter('(cn=Hubert J. Farnsworth)').first()
    assert res.name.endswith('worth')

def test_search(app):
    res = User.query.filter('(cn=Hermes Conrad)').all()
    assert isinstance(res, list)
    res = User.query.first()
    assert isinstance(res, User)

def test_create_edit_remove(app, test_name):
    ag = User(name=test_name, surname='surname')
    assert ag.name == test_name
    assert ag.email == []
    assert ag.title == ''

    assert ag.save()

    ag = User.query.filter(f'(cn={test_name})').first()
    assert ag.name == test_name
    assert ag.email == []
    assert ag.title == ''

    test_title = 'TestTitle'
    ag.title = test_title

    assert ag.save()

    ag = User.query.filter(f'(cn={test_name})').first()
    assert ag.name == test_name
    assert ag.email == []
    assert ag.title == test_title

    assert ag.delete()
    ag = User.query.filter(f'(cn={test_name})').first()
    assert not ag


def test_fail_delete(app):
    ag = User(cn='non-existant')
    assert not ag.delete()

def test_copy(entry):
    import copy
    copy.copy(entry)

def test_is_list(test_name):
    ag = User(name=test_name, surname='surname')
    assert ag.save()

    res = User.query.filter(f'(cn={test_name})').first()
    assert res.email == []

def test_modify(app, test_name):
    ag = User(name=test_name, surname='surname')
    ag.save()

    ag = User.query.filter(f'(cn={test_name})').first()
    ag.title = ''
    ag.save()

    ag = User.query.filter(f'(cn={test_name})').first()
    ag.description = 'lol2'
    ag.save()
    ag.delete()

def test_save_twice(app, test_name):
    ag = User(name=test_name, surname='surname')
    ag.save()
    ag.title = '1337'
    ag.save()
    ag.title = '1338'
    ag.save()

    assert ag.title == '1338'

    ag = User.query.filter(f'(cn={test_name})').first()
    assert ag.title == '1338'

def test_save_delete_save(app, test_name):
    ag = User(name=test_name, surname='surname')
    ag.save()
    ag.delete()
    ag.save()
    assert User.query.filter(f'(cn={test_name})').first()

def test_fetch_delete_save(app, test_name):
    ag = User(name=test_name, surname='surname')
    ag.save()

    ag = User.query.filter(f'(cn={test_name})').first()
    ag.delete()
    ag.save()

def test_delete(app, test_name):
    ag = User(name=test_name, surname='surname')
    ag.save()
    ag.title = 'lol'
    ag.save()
    assert User.query.filter(f'(cn={test_name})').first().title == 'lol'
    ag.title = ''
    ag.save()
    assert User.query.filter(f'(cn={test_name})').first().title == ''
    ag.title = 'lol'
    ag.save()
    assert User.query.filter(f'(cn={test_name})').first().title == 'lol'
