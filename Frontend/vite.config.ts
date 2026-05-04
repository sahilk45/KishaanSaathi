import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const uppercaseJsonPlugin = () => ({
  name: 'uppercase-json-loader',
  transform(code: string, id: string) {
    if (!id.endsWith('.JSON')) {
      return null
    }

    return {
      code: `export default ${code}`,
      map: null,
    }
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), uppercaseJsonPlugin()],
})
