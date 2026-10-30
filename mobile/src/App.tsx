import { MotionConfig } from "motion/react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { NotFoundScreen } from "@/components/ErrorPage";
import { HelpScreen } from "@/screens/HelpScreen";
import { LoadingScreen } from "@/screens/LoadingScreen";
import { ResultsScreen } from "@/screens/ResultsScreen";
import { RoleTaskSelectScreen } from "@/screens/RoleTaskSelectScreen";
import { StyleguideScreen } from "@/screens/StyleguideScreen";

// Dev only: renders a component that throws, to check the crash screen
function CrashTest(): never {
  throw new Error("Deliberate crash for testing the error screen");
}

export default function App() {
  return (
    // "user": all motion animations follow the device's reduce-motion setting
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<RoleTaskSelectScreen />} />
            <Route path="/loading" element={<LoadingScreen />} />
            <Route path="/results" element={<ResultsScreen />} />
            <Route path="/hilfe" element={<HelpScreen />} />
            {import.meta.env.DEV && <Route path="/dev/styleguide" element={<StyleguideScreen />} />}
            {import.meta.env.DEV && <Route path="/dev/crash" element={<CrashTest />} />}
            <Route path="*" element={<NotFoundScreen />} />
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </MotionConfig>
  );
}
