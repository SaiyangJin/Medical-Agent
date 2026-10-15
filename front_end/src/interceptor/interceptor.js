import {ElMessage} from "element-plus";
import {axiosInstance} from "../axios/axios.js";


axiosInstance.interceptors.response.use((response)=>{
    const data = response.data;
    console.log("返回结果的数据是",data)
    //{"code":200,{"code":200,"data":"114",msg:""}}
    if(data.code!==200){
        ElMessage.error(data.msg)
        return Promise.reject()
    }
    return data.data;
},  (error) => {
    if (error.response) {
        console.error("未捕获的系统错误", error.response.data)
        ElMessage.error("未捕获的系统错误")
    } else {
        ElMessage.error("网络异常，检查后端是否启动")
    }
    return Promise.reject(error)
})