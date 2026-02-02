function getActionFromHash() {
  const hash = window.location.hash || "";
  if (!hash.includes("?")) return null;

  const queryString = hash.split("?")[1];
  return new URLSearchParams(queryString).get("action");
}

export async function initApp(app) {
  try {
    // 1️⃣ Get config from Flask
    const res = await fetch("http://localhost:5050/runtime-config");
    const config = await res.json();

    const ERP_BASE_URL = config.erp_url.replace(/\/$/, "");
    const ERP_TEST_METHOD =
      "/api/method/factory_auth.factory_authentication.api.connection_test.test_erp_url";

    const ERP_TEST_URL =
      `${ERP_BASE_URL}${ERP_TEST_METHOD}?erp_url=${encodeURIComponent(ERP_BASE_URL)}`;

    app.config.globalProperties.$ERP_TEST_URL = ERP_TEST_URL;

    console.log("INIT ERP_TEST_URL:", ERP_TEST_URL);

    const action = getActionFromHash();

    if (action === "test") {
      console.log("🧪 TEST requested from plugin");

      let success = false;

      try {
        // 🔥 ADD TIMEOUT
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const testRes = await fetch(ERP_TEST_URL, {
          method: "GET",
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (testRes.ok) {
          const testData = await testRes.json();
          success = testData?.message?.status === "ok";
        }

      } catch (err) {
        console.error("❌ ERP test failed:", err);
        success = false;
      }

      app.config.globalProperties.$ERP_CONNECTED = success;

      console.log("🔗 ERP connection:", success ? "OK" : "FAILED");

      // ✅ ALWAYS notify Flask (success OR failure)
      await fetch("http://localhost:5050/save-erp-test-result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          success,
          timestamp: Date.now()
        })
      });

      console.log("📤 ERP test result sent to Flask:", success);
    }

  } catch (err) {
    console.error("❌ INIT failed:", err);

    // Fallback failure notification
    await fetch("http://localhost:5050/save-erp-test-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        success: false,
        error: err.message,
        timestamp: Date.now()
      })
    });
  }
}
