import datetime
import traceback
def boom():
    return 1/0

def test():
    trace_list = []
    start_time=datetime.datetime.now()
    error=None
    trace_id = "test114514"
    result=None
    try:
        result=boom()
    except Exception :
        error=str(traceback.format_exc())
    finally:
        end_time = datetime.datetime.now()
        #两个相减是duration类，所以要提取出秒数
        print(f"方法:{boom.__name__} 耗时: {(end_time - start_time).total_seconds()} 秒")
        document = {"node_name": boom.__name__,
                    "result": result,
                    "trace_id": trace_id,
                    "error": error,
                    "start_time": start_time,
                    "end_time": end_time,
                    "cost_time": (end_time - start_time).total_seconds(),  # 时间类型相减
                    "is_deleted": False
                    }
        trace_list.append(document)
        print(trace_list)