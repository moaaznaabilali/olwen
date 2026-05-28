// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  runtimeConfig: {
    public: {
      // Olwen backend (FastAPI). Override with NUXT_PUBLIC_API_BASE.
      apiBase: 'http://127.0.0.1:8000',
    },
  },
})
