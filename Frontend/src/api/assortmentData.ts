import type { AssortmentData } from '../types/assortment'

export async function loadAssortmentData(): Promise<AssortmentData> {
  const res = await fetch('/data/assortment_data.json', { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to load workspace data: ${res.status}`)
  return (await res.json()) as AssortmentData
}
