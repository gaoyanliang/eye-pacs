import logging

import pymysql
from pymysql.cursors import DictCursor

from gylmodules import global_config

logger = logging.getLogger(__name__)

"""
数据库工具类
"""


class DbUtil:
    """构造函数"""

    def __init__(self, host: str, user: str, password: str, database: str, port: int = 3306):
        """
        mysql 连接配置
        :param host:
        :param port:
        :param user:
        :param password:
        :param database:
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.__conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database)
        # Create a cursor with DictCursor
        self.__cursor = self.__conn.cursor(cursor=DictCursor)
        # log.debug(f'connect db: {host}=, {port}=, {user}=, {password}=, {database}=')

    def __del__(self):
        """析构函数"""
        if self.__cursor is not None:
            self.__cursor.close()
        if self.__conn is not None:
            self.__conn.close()
        # log.debug("close db!")

    def get_conn(self):
        """获取连接"""
        return self.__conn

    def get_cursor(self, cursor=None):
        """获取游标"""
        return self.__conn.cursor(cursor)

    def __commit(self):
        """提交改动"""
        self.__conn.commit()

    def get_version(self, args=None):
        """获取 DB 版本"""
        self.__cursor.execute("SELECT VERSION()", args)
        version = self.__cursor.fetchone()
        logger.info(f'DB Version : {version}=')
        return version

    def list_databases(self, args=None):
        """查询所有数据库"""
        self.__cursor.execute("SHOW DATABASES", args)
        dbs = []
        for db in self.__cursor.fetchall():
            dbs.append(db)
        return dbs

    def list_tables(self, args=None):
        """查询所有表"""
        self.__cursor.execute("SHOW TABLES", args)
        tables = []
        for table in self.__cursor.fetchall():
            tables.append(table)
        return tables

    def get_table_fields(self, db, table, args=None):
        """获取表字段信息"""
        sql = 'SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE table_schema="'+db+'" AND table_name="'+table+'"'
        self.__cursor.execute(sql, args)
        fields = []
        for field in self.__cursor.fetchall():
            fields.append(field)
        return fields

    def table_metadata(self, db, table, args=None):
        """查询表字段的元数据信息"""
        db = "'" + db + "'"
        table = "'" + table + "'"
        sql = """
        SELECT 
            column_name,column_type,ordinal_position,column_comment,column_default 
        FROM 
            information_schema.COLUMNS 
        WHERE 
            table_schema = %s AND table_name = %s;
        """ % (db, table)
        self.__cursor.execute(sql, args)
        return self.__cursor.fetchall()

    def select_db(self, db):
        """选择数据库"""
        self.__conn.select_db(db)
        logger.info(f'switch database to {db}=')

    def execute(self, sql, args=None, need_commit: bool = False, print_log: bool = True):
        """获取SQL执行结果"""
        try:
            self.__cursor.execute(sql, args)
            last_rowid = self.__cursor.lastrowid
            if need_commit:
                self.__commit()
            return last_rowid
        except Exception as e:
            if print_log:
                logger.warning(f"执行SQL {sql}, 遇到异常 {e}")
            else:
                logger.debug(f"执行SQL {sql}, 遇到异常 {e}")
            self.__conn.rollback()
        return -1

    def execute_many(self, sql, args=None, need_commit: bool = False, print_log: bool = True):
        """获取SQL执行结果"""
        try:
            self.__cursor.executemany(sql, args)
            if need_commit:
                self.__commit()

            # 获取最后一个插入记录的ID
            return self.__cursor.lastrowid
        except Exception as e:
            if print_log:
                logger.warning(f"执行SQL {sql}, 遇到异常 {e}")
            else:
                logger.debug(f"执行SQL {sql}, 遇到异常 {e}")
            self.__conn.rollback()
        return -1

    def query_one(self, sql, print_log: bool = True):
        """查询单条数据"""
        result = None
        try:
            self.__cursor.execute(sql)
            result = self.__cursor.fetchone()
        except Exception as e:
            if print_log:
                logger.warning(f"执行SQL {sql}, 遇到异常 {e}")
            else:
                logger.debug(f"执行SQL {sql}, 遇到异常 {e}")
        return result

    def query_all(self, sql, print_log: bool = True):
        """查询多条数据"""
        list_result = ()
        try:
            self.__cursor.execute(sql)
            list_result = self.__cursor.fetchall()
        except Exception as e:
            if print_log:
                logger.warning(f"执行SQL {sql}, 遇到异常 {e}")
            else:
                logger.debug(f"执行SQL {sql}, 遇到异常 {e}")
        return list_result


if __name__ == "__main__":
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD, global_config.DB_DATABASE_GYL)
    db.get_version()

    dbs = db.list_databases()
    print(f"database list: {dbs}")

    dbs = db.list_tables()
    print(f"table list: {dbs}")

    data = db.query_all("select count(*) from nsyy_gyl.cv_info")
    print(data)

    del db



