from setuptools import setup

setup(
    name='flask-python-ldap',
    version='0.1.3',
    url = 'https://github.com/jagheterfredrik/flask-python-ldap',
    author = 'Fredrik Gustafsson',
    author_email = 'jagheterfredrik@gmail.com',
    description = 'A basic ORM around python-ldap, influenced by flask-ldapconn',
    packages=[
        'flask_python_ldap'
    ],
    platforms='any',
    install_requires=[
        'flask >= 1.0.2',
        'python-ldap >= 3.1.0',
        'certifi >= certifi-2018.8.24'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Framework :: Flask',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
)
