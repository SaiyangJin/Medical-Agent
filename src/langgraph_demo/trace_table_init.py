import datetime

from sqlalchemy import (Table, MetaData, Column, Text, JSON, Boolean, DateTime,
                        TIMESTAMP, BigInteger, DOUBLE,Float)
from sqlalchemy.dialects.postgresql import JSONB

from src.parent_child_chunk.init_model import engine

meta_data = MetaData()
trace_table = Table("trace", meta_data,
              Column("id", BigInteger, primary_key=True),
              Column("node_name", Text, nullable=False),
              Column("trace_id", Text, nullable=False),
              Column("result", JSONB, nullable=True),
              Column("error", Text, nullable=True),
              Column("question", Text, nullable=True),
              Column("start_time", DateTime, nullable=False),
              Column("end_time", DateTime, nullable=False),
              Column("cost_time", Float, nullable=False),
              Column("is_deleted", Boolean, nullable=False))

request_table = Table("llm_request", meta_data,
              Column("id", BigInteger, primary_key=True),
              Column("question", Text, nullable=False),
              Column("passed", Boolean, nullable=False),
              Column("is_system_error", Boolean, nullable=False),
              Column("trace_id", Text, nullable=False),
              Column("run_id", Text, nullable=False),
              Column("fail_reason", Text, nullable=True),
              Column("create_time", TIMESTAMP, nullable=False,default=datetime.datetime.now()),
              Column("is_deleted", Boolean, nullable=False,default=False))
if __name__ == '__main__':
    #定义表

    #创建表
    # meta_data.drop_all(engine)
    meta_data.create_all(engine)