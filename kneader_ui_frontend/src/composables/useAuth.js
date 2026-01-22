// composables/useAuth.js
import { ref } from 'vue'
import { login as apiLogin } from '@/api'

const token = ref(localStorage.getItem('token'))

export function useAuth() {
  const username = ref('')
  const password = ref('')
  const showPassword = ref(false)
  const error = ref('')

  const login = async () => {
    error.value = ''
    try {
      const res = await apiLogin(username.value, password.value)
      if (res?.token) {
        localStorage.setItem('token', res.token)
        token.value = res.token
        return true
      }
      error.value = 'Invalid ERPNext credentials'
      return false
    } catch (e) {
      error.value = 'Login failed. Please check your credentials.'
      return false
    }
  }

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('lastBatchType')
    localStorage.removeItem('lastBatchNumber')
    token.value = null
  }

  return {
    token,
    username,
    password,
    showPassword,
    error,
    login,
    logout
  }
}
