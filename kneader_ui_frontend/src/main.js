import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { initApp } from './init'   

const app = createApp(App)

await initApp(app);

app.use(router);
app.mount("#app");