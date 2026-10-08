import { environment } from '../config/environment'
import type { ObservabilityResponse } from '../types/observability'

export const fetchObservability = async (accessToken: string): Promise<ObservabilityResponse> => {
  const response = await fetch(environment.apiUrl, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })

  if (!response.ok) {
    throw new Error(`Observability API returned HTTP ${response.status}`)
  }

  return response.json() as Promise<ObservabilityResponse>
}
