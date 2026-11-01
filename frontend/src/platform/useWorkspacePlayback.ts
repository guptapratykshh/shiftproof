import { useRef, useState } from "react";
export function useWorkspacePlayback() {
  const [playing, setPlaying] = useState(false);
  const audioPlayer = useRef<HTMLAudioElement | null>(null);
  const speechSequence = useRef(0);
  const speechVersion = useRef<number | null>(null);
  function stopPlayback() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    speechSequence.current += 1;
    speechVersion.current = null;
    audioPlayer.current?.pause();
    if (audioPlayer.current?.src) URL.revokeObjectURL(audioPlayer.current.src);
    audioPlayer.current = null;
    document
      .querySelectorAll(".organization-app audio")
      .forEach((a) => (a as HTMLAudioElement).pause());
    setPlaying(false);
  }
  return {
    playing,
    setPlaying,
    audioPlayer,
    speechSequence,
    speechVersion,
    stopPlayback,
  };
}
