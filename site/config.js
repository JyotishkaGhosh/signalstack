// Public settings for the site. The publishable key is meant to be shared:
// Row Level Security in Supabase decides what each signed-in user can read and change.
// Never put the secret key (sb_secret_...) here or anywhere else in the site.
window.SIGNALSTACK_CONFIG = {
  supabaseUrl: "https://ltliwylqtesptxpwoqjz.supabase.co",
  supabasePublishableKey: "sb_publishable_Zo0o9w3zheNu0b54msM9OQ_3Y3dXukG",
  // Turn on once Google is set up under Authentication > Sign In / Providers in Supabase
  googleSignIn: false,
};
