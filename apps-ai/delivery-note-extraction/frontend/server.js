import express from "express"
import { createProxyMiddleware } from "http-proxy-middleware"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const app = express()
const distPath = path.join(__dirname, "dist")
const port = Number(process.env.PORT ?? 8080)
const backendUrl = process.env.BACKEND_URL ?? ""

app.get("/config.json", (_request, response) => {
  response.json({
    apiBaseUrl: "",
  })
})

if (backendUrl) {
  app.use(
    "/api",
    createProxyMiddleware({
      target: backendUrl,
      changeOrigin: true,
      xfwd: true,
      pathRewrite: (requestPath) => `/api${requestPath}`,
      proxyTimeout: 0,
      timeout: 0,
    }),
  )
} else {
  app.use("/api", (_request, response) => {
    response.status(503).json({ error: "BACKEND_URL is not configured." })
  })
}

app.use(express.static(distPath))

app.get("*", (_request, response) => {
  response.sendFile(path.join(distPath, "index.html"))
})

app.listen(port)
