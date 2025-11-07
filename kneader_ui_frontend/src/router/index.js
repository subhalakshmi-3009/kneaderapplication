import { createRouter, createWebHashHistory } from 'vue-router'   // ✅ fixed import
import Dashboard from '../views/Dashboard.vue'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard
  }
]

const router = createRouter({
  history: createWebHashHistory(),   // ✅ matches import
  routes
})

export default router
