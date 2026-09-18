#导入区
from sqlalchemy import MetaData, create_engine, Table, Column, BigInteger, Text,insert

#链接参数
DB_URL="postgresql+psycopg://root:123456@localhost:5432/postgres"
engine = create_engine(DB_URL)
#装载表定义的容器,表定义安置在这里
metadata = MetaData()
#定义表
disease_parent_chuck_table = Table("disease_parent_chuck"  # 表名
              , metadata  # 装载到哪个表定义容器
              # 列定义：名字，类型，约束
              , Column("id", Text, primary_key=True)
              , Column("disease", Text,nullable=False)
              , Column("title", Text,nullable=False)
              , Column("text", Text,nullable=False)
              , Column("revision", Text,nullable=False))
#指定建表语句(把metadata定义的表全都建出来),加入连接池引擎
if __name__ == '__main__':
    #创建表
    metadata.drop_all(engine)
    metadata.create_all(engine)
    #插入第一条数据


