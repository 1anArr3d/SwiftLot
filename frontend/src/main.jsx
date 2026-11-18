import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './provenance/holo.css'
import './provenance/banknote.css'
import './provenance/shell.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
