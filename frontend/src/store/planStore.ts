import { create } from 'zustand'
import type { PlanSummary, PlanDetail } from '../api/client'

interface PlanState {
  plans: PlanSummary[]
  activePlan: PlanDetail | null
  loading: boolean

  setPlans: (plans: PlanSummary[]) => void
  setActivePlan: (plan: PlanDetail | null) => void
  setLoading: (v: boolean) => void
  updateActivePlan: (partial: Partial<PlanDetail>) => void
}

export const usePlanStore = create<PlanState>((set) => ({
  plans: [],
  activePlan: null,
  loading: false,

  setPlans: (plans) => set({ plans }),
  setActivePlan: (plan) => set({ activePlan: plan }),
  setLoading: (loading) => set({ loading }),
  updateActivePlan: (partial) =>
    set((s) => ({
      activePlan: s.activePlan ? { ...s.activePlan, ...partial } : null,
    })),
}))
