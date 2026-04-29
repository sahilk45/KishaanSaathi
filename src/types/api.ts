export type DistrictItem = {
  state_name: string
  dist_name: string
}

export type CropItem = {
  crop_type: string
  display_name: string
  benchmark_yield_kg_ha?: number | null
}

export type CropsResponse = {
  crops: CropItem[]
}

export type FarmerRegisterResponse = {
  farmer_id: string
  name: string
  phone: string
  state_name: string
  dist_name: string
}

export type FarmRegisterResponse = {
  field_id: string
  polygon_id: string
  area?: number | null
  source: string
  city_name?: string | null
  state_name?: string | null
  center_lat: number
  center_lon: number
}

export type HealthScoreDetail = {
  final_health_score: number
  yield_score: number
  soil_score: number
  water_score: number
  climate_score: number
  ndvi_score: number
  ndvi_source: string
  risk_level: string
  loan_decision: string
}

export type PredictResponse = {
  field_id: string
  crop_type: string
  year: number
  predicted_yield: number
  benchmark_yield?: number | null
  health: HealthScoreDetail
  kharif_temp_used: number
  kharif_rain_used: number
  rabi_temp_used: number
  wdi_used: number
  soil_score_used: number
  irr_source: string
  irrigation_used: number
  ndvi_mean?: number | null
  ndvi_max?: number | null
  soil_moisture?: number | null
  soil_temp_surface?: number | null
  air_temp?: number | null
  humidity?: number | null
  cloud_cover?: number | null
  satellite_image_date?: string | null
  satellite_source: string
  cached: boolean
  calculated_at: string
}

export type FieldHistoryResponse = {
  field_id: string
  count: number
  history: PredictResponse[]
}

export type AgroSnapshotResponse = {
  field_id: string
  polygon_id: string
  city_name?: string | null
  state_name?: string | null
  start: number
  end: number
  source: string
  latest_image_date?: string | null
  images_count: number
  ndvi_tile_url?: string | null
  ndvi_stats_url?: string | null
  ndvi_stats?: {
    mean?: number
    max?: number
    std?: number
    min?: number
  }
  weather?: {
    air_temp?: number
    humidity?: number
    cloud_cover?: number
  }
  soil?: {
    soil_moisture?: number
    soil_temp_surface?: number
  }
}
