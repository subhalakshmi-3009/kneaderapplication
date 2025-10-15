<template>
  <div id="app">
    <header class="app-header">
      <div class="header-content">
        <img src="@/assests/SPP_logo_website.png" alt="SPP Logo" class="company-logo" />
        <h1 class="app-title">Kneader Controller System</h1>
      </div>
    </header>

    <main>
      <router-view />
    </main>
  </div>
</template>

<script>
export default {
  name: 'App'
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Arial', sans-serif;
  background-color: #f5f5f5;
  color: #333;
}

.app-header {
  background-color: #2c3e50;
  color: white;
  padding: 1rem 2rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  position: relative;
}

.header-content {
  display: flex;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
  position: relative;
}

.company-logo {
  height: 60px; /* Increased size */
  width: auto;
  /* Logo will naturally align to the left in flex container */
}

.app-title {
  font-size: 1.8rem;
  font-weight: bold;
  position: absolute; /* Position absolutely to center it */
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
}

main {
  padding: 1rem;
  max-width: 1200px;
  margin: 0 auto;
}
</style>