<template>
  <div class="login-container">

    <div class="login-card">
      <div class="login-header">
        <h1 class="login-subtitle">Login to start the process</h1>
      </div>

      <div class="login-form">
        <!-- Username -->
        <div class="input-group">
          <label class="input-label">Username</label>
          <input
            v-model="username"
            class="form-input"
            placeholder="Enter your username"
            @keyup.enter="onLogin"
          />
        </div>

        <!-- Password -->
        <div class="input-group">
          <label class="input-label">Password</label>
          <div class="password-input-container">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="form-input"
              placeholder="Enter your password"
              @keyup.enter="onLogin"
            />
            <button
              type="button"
              class="password-toggle"
              @click="showPassword = !showPassword"
            >
              {{ showPassword ? 'Hide' : 'Show' }}
            </button>
          </div>
        </div>

        <!-- Button -->
        <div class="button-container">
          <button
            class="login-button"
            :disabled="!username || !password"
            @click="onLogin"
          >
            Login
          </button>
        </div>

        <!-- Error -->
        <div v-if="error" class="error-message">
          <p class="error-text">{{ error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>



<script setup>
import { useAuth } from '@/composables/useAuth'

console.log('LoginCard rendered')

const emit = defineEmits(['success'])

const {
  token,
  username,
  password,
  showPassword,
  error,
  login
} = useAuth()

const onLogin = async () => {
  const ok = await login()
  if (ok) emit('success')
}
</script>

<style scoped>
.login-screen { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; gap: 10px; } .login-screen input { padding: 8px; width: 220px; font-size: 1rem; } .login-screen button { padding: 8px 12px; font-size: 1rem; background-color: #007bff; color: white; border: none; border-radius: 4px; }/* Login Screen Styles */ .login-container { display: flex; flex-direction: column; align-items: center; justify-content: flex-start; /* Changed from center to flex-start */ min-height: 100vh; background-color: #f8f9fa; padding: 2rem; padding-top: 4rem; /* Added top padding to move card down slightly from top */ } .login-card { background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); padding: 3rem; max-width: 400px; width: 100%; border: 2px solid #060606; /* Remove any margin that might be pushing it down */ margin: 0; } .login-header { text-align: center; margin-bottom: 2.5rem; } .login-title { font-size: 1.8rem; font-weight: 600; color: #2c3e50; margin-bottom: 0.5rem; } .login-subtitle { color: #101111; font-size: 1rem; margin: 0; } .login-form { space-y: 1.5rem; } .input-group { margin-bottom: 1.5rem; } .input-label { display: block; font-weight: 500; color: #495057; margin-bottom: 0.5rem; font-size: 0.95rem; } .form-input { width: 100%; padding: 0.875rem 1rem; border: 2px solid #e9ecef; border-radius: 8px; font-size: 1rem; transition: all 0.2s ease; background: white; box-sizing: border-box; } .form-input:focus { outline: none; border-color: #007bff; box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.1); } .form-input::placeholder { color: #6c757d; } .button-container { margin-top: 2rem; display: flex; justify-content: center; } .login-button { background: #007bff; color: white; border: none; border-radius: 8px; padding: 0.875rem 2rem; font-size: 1rem; font-weight: 500; cursor: pointer; transition: all 0.2s ease; min-width: 120px; } .login-button:hover:not(.login-button-disabled) { background: #0056b3; transform: translateY(-1px); } .login-button:active:not(.login-button-disabled) { transform: translateY(0); } .login-button-disabled { background: #6c757d; cursor: not-allowed; transform: none; } .error-message { background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px; padding: 1rem; margin-top: 1.5rem; text-align: center; } .error-text { color: #721c24; margin: 0; font-weight: 500; font-size: 0.95rem; }
.password-input-container {
  position: relative;
  display: flex;
  align-items: center;
}

.password-input {
  padding-right: 60px; /* space for Show button */
}

.password-toggle {
  position: absolute;
  right: 10px;
  background: none;
  border: none;
  color: #007bff;
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0;
}

.password-toggle:hover {
  text-decoration: underline;
}

</style>

