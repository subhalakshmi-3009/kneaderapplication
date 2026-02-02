<template>
  <div style="padding: 30px; text-align: center;">
    <h2>Testing ERP Connection…</h2>
    <p>Please wait</p>
  </div>
</template>

<script>
export default {
  name: "ErpTest",
  mounted() {
    // Nothing to do here.
    // init.js already performs the test.
    console.log("ERP test page loaded");
  }
};
</script>
