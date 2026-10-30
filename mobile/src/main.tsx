import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Sign-in and PIN lock first: it must be initialised before the app renders.
import './second-look'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
