import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import "./interceptor/interceptor.js"
import ElementPlus from "element-plus"
import "element-plus/dist/index.css"

import * as ElementPlusIconsVue from '@element-plus/icons-vue'

let elementApp = createApp(App);

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    elementApp.component(key, component)
}

elementApp.use(ElementPlus)
elementApp.mount('#app')
