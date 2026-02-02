import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Dashboard3 from '../views/Dashboard3.vue'
import ErpTest from "../views/ErpTest.vue";
const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard
  },
   {
    path: "/erp-test",
    name: "ErpTest",
    component: ErpTest
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
