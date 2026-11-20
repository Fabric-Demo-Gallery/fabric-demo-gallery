import express from "express"
import { createProxyMiddleware } from "http-proxy-middleware"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const app = express()
const distPath = path.join(__dirname, "dist")
const port = Number(process.env.PORT ?? 8080)
const backendUrl = process.env.BACKEND_URL ?? ""

app.get("/healthz", (_request, response) => {
  response.json({ status: "ok" })
})

if (backendUrl) {
  app.use(
    ["/runs", "/api"],
    createProxyMiddleware({
      target: backendUrl,
      changeOrigin: true,
      xfwd: true,
      proxyTimeout: 0,
      timeout: 0,
      pathRewrite: (_requestPath, request) => request.originalUrl,
    }),
  )
} else {
  app.use(["/runs", "/api"], (_request, response) => {
    response.status(503).json({ error: "BACKEND_URL is not configured." })
  })
}

app.use(express.static(distPath))

app.get("*", (_request, response) => {
  response.sendFile(path.join(distPath, "index.html"))
})

app.listen(port)
