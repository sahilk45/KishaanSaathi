import type { AgroSnapshotResponse, ApmcMasterResponse, ApmcPricesResponse, CropsResponse, DistrictItem, FarmerFieldsResponse, FieldHistoryResponse, FarmerRegisterResponse, FarmRegisterResponse, PredictResponse } from '../types/api'

export type ApiErrorDetail = {
  status: number
  detail: string
}

export type PredictPayload = {
  field_id: string
  crop_type: string
  npk_input: number
  year: number
  irrigation_ratio?: number | null
}

export type FarmerRegisterPayload = {
  google_sub: string
  name: string
  phone: string
  state_name: string
  dist_name: string
  email?: string
  email_verified?: boolean
  picture?: string
}

export type FarmRegisterPayload = {
  farmer_id: string
  field_name: string
  coordinates: number[][]
  area_hectares?: number | null
}

const apiBaseUrl = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000').replace(
  /\/+$/,
  '',
)

const buildErrorDetail = (status: number, detail: unknown) => {
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          const message = (item as { msg?: unknown }).msg
          if (typeof message === 'string') return message
        }
        return ''
      })
      .filter(Boolean)
    if (messages.length) {
      return messages.join('; ')
    }
  }
  return `Request failed (${status})`
}

const request = async <T>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
    ...options,
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
    const detail = buildErrorDetail(response.status, payload?.detail)
    const error: ApiErrorDetail = { status: response.status, detail }
    throw error
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export const apiClient = {
  getDistricts: () => request<DistrictItem[]>('/districts'),
  getCrops: () => request<CropsResponse>('/crops'),
  registerFarmer: (payload: FarmerRegisterPayload) =>
    request<FarmerRegisterResponse>('/farmers/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  registerFarm: (payload: FarmRegisterPayload) =>
    request<FarmRegisterResponse>('/farm/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getFarmerFields: (farmerId: string) =>
    request<FarmerFieldsResponse>(`/farmer/${farmerId}/fields`),
  getAgroSnapshot: (fieldId: string, start?: number, end?: number) => {
    const query = new URLSearchParams()
    if (typeof start === 'number') query.set('start', `${start}`)
    if (typeof end === 'number') query.set('end', `${end}`)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<AgroSnapshotResponse>(`/field/${fieldId}/agro-snapshot${suffix}`)
  },
  getFieldHistory: (fieldId: string) => request<FieldHistoryResponse>(`/field/${fieldId}/history`),
  predict: (payload: PredictPayload, dryRun = false) => {
    const suffix = dryRun ? '?dry_run=true' : ''
    return request<PredictResponse>(`/predict${suffix}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  // ── APMC Market endpoints ──────────────────────────────────────────────
  getApmcMaster: () => request<ApmcMasterResponse>('/apmc/master'),
  getApmcPrices: (farmerId: string, commodity: string) => {
    const query = new URLSearchParams({ farmer_id: farmerId, commodity })
    return request<ApmcPricesResponse>(`/apmc/prices?${query.toString()}`)
  },
}

export const streamChat = async (
  farmerId: string,
  message: string,
  threadId: string,
  onToken: (token: string) => void,
) => {
  const response = await fetch(`${apiBaseUrl}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      farmer_id: farmerId,
      message,
      thread_id: threadId,
    }),
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
    const detail = buildErrorDetail(response.status, payload?.detail)
    const error: ApiErrorDetail = { status: response.status, detail }
    throw error
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw { status: 500, detail: 'Streaming response unavailable.' } as ApiErrorDetail
  }

  const decoder = new TextDecoder()
  let done = false

  while (!done) {
    const result = await reader.read()
    done = result.done
    if (result.value) {
      const chunk = decoder.decode(result.value, { stream: true })
      if (chunk) {
        onToken(chunk)
      }
    }
  }
}
