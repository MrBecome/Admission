# PyMySQL is used as the MySQL driver (see requirements.txt) instead of
# mysqlclient, which needs a C compiler and system headers to install.
# Django's mysql backend expects the MySQLdb module specifically, so this
# shim makes PyMySQL present itself as that module. Must run before
# django.db.backends.mysql is ever imported, hence living here in the
# project package's __init__.py, which Django loads first.
import pymysql
pymysql.install_as_MySQLdb()
