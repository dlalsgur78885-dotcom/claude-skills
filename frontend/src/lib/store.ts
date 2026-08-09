import { create } from "zustand";
import type { User, Channel, Carousel } from "./types";

interface AppState {
  user: User | null;
  channels: Channel[];
  currentCarousel: Carousel | null;

  setUser: (user: User | null) => void;
  setChannels: (channels: Channel[]) => void;
  setCurrentCarousel: (carousel: Carousel | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  user: null,
  channels: [],
  currentCarousel: null,

  setUser: (user) => set({ user }),
  setChannels: (channels) => set({ channels }),
  setCurrentCarousel: (carousel) => set({ currentCarousel: carousel }),
}));
