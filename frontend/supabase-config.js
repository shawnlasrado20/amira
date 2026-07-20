(function () {
  var SUPABASE_URL = "https://smommrlnpmnumrzeozoz.supabase.co";
  var SUPABASE_PUBLISHABLE_KEY = "sb_publishable_TRUFrcv_LLAFu1YwrwQn1w_C2mnKKbx";

  if (!window.supabase || !window.supabase.createClient) {
    console.error("Supabase client library did not load.");
    return;
  }

  window.amiraSupabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
  });
})();
