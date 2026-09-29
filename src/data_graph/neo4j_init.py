from neo4j import GraphDatabase

neo4j_driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j114514"))

#定义一个删除neo4j所有数据的方法
def delete_all_data():
    with neo4j_driver as driver:
        driver.execute_query("match (n)-[p]->(m) detach delete n,p,m")

if __name__ == '__main__':
    delete_all_data()