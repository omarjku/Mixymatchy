import { MotionConfig } from "motion/react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useLocale } from "@/i18n/locale";
import { LoadingScreen } from "@/screens/LoadingScreen";
import { ResultsScreen } from "@/screens/ResultsScreen";
import { RoleTaskSelectScreen } from "@/screens/RoleTaskSelectScreen";
import { StyleguideScreen } from "@/screens/StyleguideScreen";

export default function App() {
  // Changing the language remounts the screens so every label re-renders; route state is kept.
  const locale = useLocale();
  return (
    // "user": all motion animations follow the device's reduce-motion setting
    <MotionConfig reducedMotion="user">
      <BrowserRouter key={locale}>
        <Routes>
          <Route path="/" element={<RoleTaskSelectScreen />} />
          <Route path="/loading" element={<LoadingScreen />} />
          <Route path="/results" element={<ResultsScreen />} />
          {import.meta.env.DEV && <Route path="/dev/styleguide" element={<StyleguideScreen />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </MotionConfig>
  );
}
