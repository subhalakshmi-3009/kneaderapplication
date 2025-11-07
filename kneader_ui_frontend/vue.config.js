const { defineConfig } = require('@vue/cli-service')

module.exports = defineConfig({
  transpileDependencies: true,

  // ✅ Tell Vue to load assets from Frappe’s /assets/kneader/ path
  publicPath: '/assets/kneader/',

  devServer: {
    port: 8080
  }
})
