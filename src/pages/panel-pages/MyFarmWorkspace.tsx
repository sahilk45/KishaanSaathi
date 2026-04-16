import { LocateFixed, Save, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import MapboxDraw from '@mapbox/mapbox-gl-draw'
import '@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { PanelItem } from './panelConfig'

type Coordinates = number[][][]

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

type DrawEventType = 'draw.create' | 'draw.update' | 'draw.delete'
type DrawEventHandler = () => void
type DrawEventedMap = {
  on: (eventName: DrawEventType, handler: DrawEventHandler) => void
  off: (eventName: DrawEventType, handler: DrawEventHandler) => void
}

type GeolocateEvent = {
  coords: GeolocationCoordinates
}

type FarmRegisterResponse = {
  field_id: string
  polygon_id: string
  area?: number
  source: string
  city_name?: string | null
  state_name?: string | null
  center_lat: number
  center_lon: number
}

type FarmerRegisterResponse = {
  farmer_id: string
  name: string
  phone: string
  state_name: string
  dist_name: string
}

type AgroSnapshotResponse = {
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

const DEFAULT_CENTER: [number, number] = [76.7794, 30.7333]
const DEFAULT_ZOOM = 12
const MAPBOX_STYLE = 'mapbox://styles/mapbox/satellite-streets-v12'
const NDVI_SOURCE_ID = 'ks-ndvi-overlay-source'
const NDVI_LAYER_ID = 'ks-ndvi-overlay-layer'
const FARMER_ID_STORAGE_KEY = 'ks_last_farmer_id'

const ensureClosedRing = (ring: number[][]): number[][] => {
  if (ring.length < 3) return ring

  const first = ring[0]
  const last = ring[ring.length - 1]
  if (first[0] === last[0] && first[1] === last[1]) return ring
  return [...ring, first]
}

const toLocationId = (latitude: number, longitude: number) =>
  `loc_${latitude.toFixed(5)}_${longitude.toFixed(5)}`

const currentUnixRange = () => {
  const end = Math.floor(Date.now() / 1000)
  const start = end - 30 * 24 * 60 * 60
  return { start, end }
}

const localMockSnapshot = (fieldId: string, polygonId: string, start: number, end: number): AgroSnapshotResponse => {
  const mean = Number((0.35 + Math.random() * 0.35).toFixed(3))
  const max = Number(Math.min(0.98, mean + 0.1 + Math.random() * 0.12).toFixed(3))

  return {
    field_id: fieldId,
    polygon_id: polygonId,
    source: 'mock-local-fallback',
    start,
    end,
    latest_image_date: new Date().toISOString().slice(0, 10),
    images_count: 0,
    ndvi_tile_url: null,
    ndvi_stats_url: null,
    ndvi_stats: {
      mean,
      max,
      std: Number((0.02 + Math.random() * 0.08).toFixed(3)),
      min: Number(Math.max(0, mean - (0.06 + Math.random() * 0.05)).toFixed(3)),
    },
    weather: {
      air_temp: Number((22 + Math.random() * 12).toFixed(1)),
      humidity: Number((45 + Math.random() * 30).toFixed(1)),
      cloud_cover: Number((5 + Math.random() * 70).toFixed(1)),
    },
    soil: {
      soil_moisture: Number((0.08 + Math.random() * 0.32).toFixed(3)),
      soil_temp_surface: Number((24 + Math.random() * 10).toFixed(1)),
    },
  }
}

const buildQuickFarmerPhone = () => {
  const seed = `${Date.now()}${Math.floor(Math.random() * 1000)
    .toString()
    .padStart(3, '0')}`
  return `9${seed.slice(-9)}`
}

const parseErrorDetail = (detail: unknown, fallback: string) => {
  if (Array.isArray(detail)) {
    const joined = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          const message = (item as { msg?: unknown }).msg
          if (typeof message === 'string') return message
        }
        return 'Validation error'
      })
      .join('; ')

    return joined || fallback
  }

  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  return fallback
}

const MyFarmWorkspace = ({ item }: { item: PanelItem }) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const drawRef = useRef<MapboxDraw | null>(null)
  const polygonBoundsRef = useRef<[[number, number], [number, number]] | null>(null)

  const [farmerId, setFarmerId] = useState(() => {
    if (typeof window === 'undefined') return ''
    return window.localStorage.getItem(FARMER_ID_STORAGE_KEY) ?? ''
  })
  const [fieldName, setFieldName] = useState('My Field')
  const [areaHectares, setAreaHectares] = useState('')

  const [polygonCoordinates, setPolygonCoordinates] = useState<Coordinates | null>(null)
  const [fieldId, setFieldId] = useState<string | null>(null)
  const [polygonId, setPolygonId] = useState<string | null>(null)
  const [polygonCity, setPolygonCity] = useState<string | null>(null)
  const [polygonState, setPolygonState] = useState<string | null>(null)

  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [saveMessage, setSaveMessage] = useState('Draw a polygon, then click Save boundary.')

  const [location, setLocation] = useState<{ latitude: number; longitude: number } | null>(null)
  const [locationStatus, setLocationStatus] = useState<'idle' | 'locating' | 'found' | 'error'>('idle')
  const [locationMessage, setLocationMessage] = useState('Use current location to jump directly to your land.')

  const [snapshot, setSnapshot] = useState<AgroSnapshotResponse | null>(null)
  const [snapshotStatus, setSnapshotStatus] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [snapshotMessage, setSnapshotMessage] = useState('NDVI overlay will appear after boundary save.')

  const mapboxToken = (import.meta.env.VITE_MAPBOX_TOKEN as string | undefined) ?? 'pk.DUMMY_MAPBOX_TOKEN_REPLACE_ME'
  const apiBaseUrl = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000').replace(
    /\/+$/,
    '',
  )

  const usingDummyToken = mapboxToken.includes('DUMMY') || mapboxToken.includes('dummy')

  const mapBlock = item.blocks.find((block) => block.id === 'mapbox-canvas')
  const polygonToolsBlock = item.blocks.find((block) => block.id === 'polygon-tools')
  const ndviOverlayBlock = item.blocks.find((block) => block.id === 'ndvi-overlay')

  const coordinateRing = useMemo(() => polygonCoordinates?.[0] ?? [], [polygonCoordinates])
  const currentLocationId = useMemo(
    () => (location ? toLocationId(location.latitude, location.longitude) : 'N/A'),
    [location],
  )

  const setFarmerIdWithCache = useCallback((value: string) => {
    setFarmerId(value)

    if (typeof window === 'undefined') return

    const normalized = value.trim()
    if (normalized) {
      window.localStorage.setItem(FARMER_ID_STORAGE_KEY, normalized)
    } else {
      window.localStorage.removeItem(FARMER_ID_STORAGE_KEY)
    }
  }, [])

  const registerQuickFarmer = useCallback(async () => {
    const response = await fetch(`${apiBaseUrl}/farmers/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: 'My Farm User',
        phone: buildQuickFarmerPhone(),
        state_name: 'Punjab',
        dist_name: 'ludhiana',
      }),
    })

    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
      const detailMessage = parseErrorDetail(payload?.detail, `Could not create Farmer ID (${response.status})`)
      throw new Error(detailMessage)
    }

    const payload = (await response.json()) as FarmerRegisterResponse
    if (!payload.farmer_id) {
      throw new Error('Farmer registration succeeded but no farmer_id was returned.')
    }

    setFarmerIdWithCache(payload.farmer_id)
    return payload.farmer_id
  }, [apiBaseUrl, setFarmerIdWithCache])

  const updateNdviOverlayOnMap = useCallback((tileUrl?: string | null) => {
    const map = mapRef.current
    const bounds = polygonBoundsRef.current

    if (!map || !bounds) return

    if (map.getLayer(NDVI_LAYER_ID)) {
      map.removeLayer(NDVI_LAYER_ID)
    }
    if (map.getSource(NDVI_SOURCE_ID)) {
      map.removeSource(NDVI_SOURCE_ID)
    }

    if (!tileUrl) {
      return
    }

    map.addSource(NDVI_SOURCE_ID, {
      type: 'raster',
      tiles: [tileUrl],
      tileSize: 256,
      bounds: [bounds[0][0], bounds[0][1], bounds[1][0], bounds[1][1]],
    })

    map.addLayer({
      id: NDVI_LAYER_ID,
      type: 'raster',
      source: NDVI_SOURCE_ID,
      paint: {
        'raster-opacity': 0.45,
      },
    })
  }, [])

  const fetchAgroSnapshot = useCallback(
    async (savedFieldId: string, savedPolygonId: string) => {
      const { start, end } = currentUnixRange()
      setSnapshotStatus('loading')
      setSnapshotMessage('Loading NDVI/weather/soil snapshot...')

      try {
        const response = await fetch(`${apiBaseUrl}/field/${savedFieldId}/agro-snapshot?start=${start}&end=${end}`)
        if (!response.ok) {
          if (response.status === 404) {
            const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
            if (payload?.detail === 'Not Found') {
              const fallback = localMockSnapshot(savedFieldId, savedPolygonId, start, end)
              setSnapshot(fallback)
              setSnapshotStatus('loaded')
              setSnapshotMessage(
                'Live snapshot endpoint is unavailable on this backend instance. Showing local mock NDVI metrics.',
              )
              updateNdviOverlayOnMap(null)
              return
            }
          }
          throw new Error(`Agro snapshot request failed (${response.status})`)
        }

        const payload = (await response.json()) as AgroSnapshotResponse
        setSnapshot(payload)
        setSnapshotStatus('loaded')
        setSnapshotMessage(
          payload.ndvi_tile_url
            ? 'NDVI tile overlay applied on map.'
            : 'Snapshot loaded, but NDVI tile URL is unavailable for this time window.',
        )

        updateNdviOverlayOnMap(payload.ndvi_tile_url)
      } catch (error) {
        setSnapshotStatus('error')
        setSnapshotMessage(error instanceof Error ? error.message : 'Failed to load agro snapshot.')
      }
    },
    [apiBaseUrl, updateNdviOverlayOnMap],
  )

  const savePolygonToBackend = useCallback(
    async (coordinates: Coordinates) => {
      let normalizedFarmerId = farmerId.trim()
      if (!normalizedFarmerId) {
        setSaveStatus('saving')
        setSaveMessage('No Farmer ID detected. Creating a quick farmer profile...')

        try {
          normalizedFarmerId = await registerQuickFarmer()
          setSaveMessage('Farmer profile created. Saving polygon to backend...')
        } catch (error) {
          setSaveStatus('error')
          setSaveMessage(error instanceof Error ? error.message : 'Unable to create Farmer ID automatically.')
          return
        }
      }

      const ring = coordinates[0]
      if (!ring || ring.length < 4) {
        setSaveStatus('error')
        setSaveMessage('Polygon requires at least 4 points (including closure).')
        return
      }

      let parsedArea: number | undefined
      if (areaHectares.trim()) {
        parsedArea = Number(areaHectares)
        if (!Number.isFinite(parsedArea) || parsedArea <= 0) {
          setSaveStatus('error')
          setSaveMessage('Area hectares must be a positive number.')
          return
        }
      }

      setSaveStatus('saving')
      setSaveMessage('Saving polygon to backend...')

      try {
        const response = await fetch(`${apiBaseUrl}/farm/register`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            farmer_id: normalizedFarmerId,
            field_name: fieldName.trim() || 'My Field',
            coordinates: ensureClosedRing(ring),
            area_hectares: parsedArea,
          }),
        })

        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
          throw new Error(parseErrorDetail(payload?.detail, `Request failed with status ${response.status}`))
        }

        const payload = (await response.json()) as FarmRegisterResponse
        setFieldId(payload.field_id)
        setPolygonId(payload.polygon_id)
        setPolygonCity(payload.city_name ?? null)
        setPolygonState(payload.state_name ?? null)
        setSaveStatus('saved')
        setSaveMessage(`Boundary saved. Field ${payload.field_id}, Polygon ${payload.polygon_id}.`)

        await fetchAgroSnapshot(payload.field_id, payload.polygon_id)
      } catch (error) {
        setSaveStatus('error')
        setSaveMessage(error instanceof Error ? error.message : 'Could not save polygon to backend.')
        console.error('Polygon save failed:', error)
      }
    },
    [apiBaseUrl, areaHectares, farmerId, fieldName, fetchAgroSnapshot, registerQuickFarmer],
  )

  const syncFromDraw = useCallback(() => {
    const draw = drawRef.current
    if (!draw) return

    const allFeatures = draw.getAll().features
    const polygonFeature = allFeatures.find((feature) => feature.geometry.type === 'Polygon')

    if (!polygonFeature || polygonFeature.geometry.type !== 'Polygon') {
      setPolygonCoordinates(null)
      polygonBoundsRef.current = null
      setFieldId(null)
      setPolygonId(null)
      setPolygonCity(null)
      setPolygonState(null)
      setSnapshot(null)
      setSnapshotStatus('idle')
      setSnapshotMessage('NDVI overlay will appear after boundary save.')
      setSaveStatus('idle')
      setSaveMessage('No polygon selected. Draw one to continue.')
      updateNdviOverlayOnMap(null)
      return
    }

    const coordinates = polygonFeature.geometry.coordinates as Coordinates
    const ring = coordinates[0] ?? []

    const lons = ring.map((point) => point[0])
    const lats = ring.map((point) => point[1])

    if (lons.length > 0 && lats.length > 0) {
      polygonBoundsRef.current = [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ]
    }

    setPolygonCoordinates(coordinates)
    setSnapshot(null)
    setSnapshotStatus('idle')
    setSnapshotMessage('Polygon captured. Click Save boundary to persist and load NDVI.')
    setSaveStatus('idle')
    setSaveMessage('Polygon captured. Click Save boundary to persist it.')
    updateNdviOverlayOnMap(null)
  }, [updateNdviOverlayOnMap])

  const handleSaveCurrentPolygon = useCallback(async () => {
    if (!polygonCoordinates) {
      setSaveStatus('error')
      setSaveMessage('Draw a polygon first, then save it.')
      return
    }
    await savePolygonToBackend(polygonCoordinates)
  }, [polygonCoordinates, savePolygonToBackend])

  const handleLocateUser = useCallback(() => {
    const map = mapRef.current
    if (!map) return

    if (!navigator.geolocation) {
      setLocationStatus('error')
      setLocationMessage('Geolocation is not supported by this browser.')
      return
    }

    setLocationStatus('locating')
    setLocationMessage('Fetching your current location...')

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        setLocation({ latitude, longitude })
        setLocationStatus('found')
        setLocationMessage('Current location detected successfully.')

        map.flyTo({
          center: [longitude, latitude],
          zoom: 15,
          essential: true,
        })
      },
      (error) => {
        setLocationStatus('error')
        setLocationMessage(error.message || 'Unable to access current location.')
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
      },
    )
  }, [])

  const clearPolygon = useCallback(() => {
    const draw = drawRef.current
    if (!draw) return

    draw.deleteAll()
    polygonBoundsRef.current = null
    setPolygonCoordinates(null)
    setFieldId(null)
    setPolygonId(null)
    setPolygonCity(null)
    setPolygonState(null)
    setSnapshot(null)
    setSnapshotStatus('idle')
    setSnapshotMessage('NDVI overlay will appear after boundary save.')
    setSaveStatus('idle')
    setSaveMessage('Polygon cleared. Draw a new boundary.')
    updateNdviOverlayOnMap(null)
  }, [updateNdviOverlayOnMap])

  useEffect(() => {
    const container = mapContainerRef.current
    if (!container) return

    mapboxgl.accessToken = mapboxToken

    const map = new mapboxgl.Map({
      container,
      style: MAPBOX_STYLE,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
    })

    mapRef.current = map

    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')

    const geolocateControl = new mapboxgl.GeolocateControl({
      positionOptions: {
        enableHighAccuracy: true,
      },
      trackUserLocation: true,
      showUserHeading: true,
    })

    map.addControl(geolocateControl, 'top-right')

    const draw = new MapboxDraw({
      displayControlsDefault: false,
      controls: {
        polygon: true,
        trash: true,
      },
    })

    drawRef.current = draw
    map.addControl(draw, 'top-left')

    const drawCreateHandler = () => {
      syncFromDraw()
    }

    const drawUpdateHandler = () => {
      syncFromDraw()
    }

    const drawDeleteHandler = () => {
      polygonBoundsRef.current = null
      setPolygonCoordinates(null)
      setFieldId(null)
      setPolygonId(null)
      setPolygonCity(null)
      setPolygonState(null)
      setSnapshot(null)
      setSnapshotStatus('idle')
      setSnapshotMessage('NDVI overlay will appear after boundary save.')
      setSaveStatus('idle')
      setSaveMessage('Polygon deleted. Draw a new one anytime.')
      updateNdviOverlayOnMap(null)
    }

    const drawEventedMap = map as unknown as DrawEventedMap
    drawEventedMap.on('draw.create', drawCreateHandler)
    drawEventedMap.on('draw.update', drawUpdateHandler)
    drawEventedMap.on('draw.delete', drawDeleteHandler)

    geolocateControl.on('geolocate', (event: GeolocateEvent) => {
      const coords = event.coords
      setLocation({ latitude: coords.latitude, longitude: coords.longitude })
      setLocationStatus('found')
      setLocationMessage('Tracking your current position.')
    })

    geolocateControl.on('error', () => {
      setLocationStatus('error')
      setLocationMessage('Location permission denied or unavailable.')
    })

    return () => {
      drawEventedMap.off('draw.create', drawCreateHandler)
      drawEventedMap.off('draw.update', drawUpdateHandler)
      drawEventedMap.off('draw.delete', drawDeleteHandler)
      map.remove()
      mapRef.current = null
      drawRef.current = null
    }
  }, [mapboxToken, syncFromDraw, updateNdviOverlayOnMap])

  return (
    <div className="panel-cards panel-cards--my-farm">
      <article id={mapBlock?.id ?? 'mapbox-canvas'} className="panel-card panel-card--mapbox">
        <div className="panel-card__head">
          <h3>{mapBlock?.title ?? 'Mapbox Canvas'}</h3>
          <span className="panel-card__metric">Live map</span>
        </div>
        <p>{mapBlock?.description ?? 'Interactive map for location and farm boundary drawing.'}</p>

        <div className="panel-myfarm-form">
          <label className="panel-myfarm-field">
            Farmer ID (UUID)
            <input
              type="text"
              value={farmerId}
              onChange={(event) => setFarmerIdWithCache(event.target.value)}
              placeholder="Paste farmer_id from /farmers/register"
            />
          </label>
          <label className="panel-myfarm-field">
            Field name
            <input type="text" value={fieldName} onChange={(event) => setFieldName(event.target.value)} />
          </label>
          <label className="panel-myfarm-field">
            Area (hectares, optional)
            <input
              type="number"
              min="0"
              step="0.01"
              value={areaHectares}
              onChange={(event) => setAreaHectares(event.target.value)}
              placeholder="1.4"
            />
          </label>
        </div>
        <p className="panel-myfarm-feedback panel-myfarm-feedback--muted">
          Tip: you can leave Farmer ID empty — it will be auto-created on Save boundary.
        </p>

        <div className="panel-mapbox">
          <div ref={mapContainerRef} className="panel-mapbox__canvas" aria-label="My Farm map canvas" />

          <div className="panel-mapbox__actions">
            <button type="button" className="panel-mapbox__button" onClick={handleLocateUser}>
              <LocateFixed size={15} aria-hidden="true" />
              Track current location
            </button>
            <button type="button" className="panel-mapbox__button" onClick={handleSaveCurrentPolygon}>
              <Save size={15} aria-hidden="true" />
              Save boundary
            </button>
            <button type="button" className="panel-mapbox__button panel-mapbox__button--ghost" onClick={clearPolygon}>
              <Trash2 size={15} aria-hidden="true" />
              Clear polygon
            </button>
          </div>

          {usingDummyToken ? (
            <p className="panel-mapbox__notice">
              Using dummy Mapbox token. Update <code>VITE_MAPBOX_TOKEN</code> in <code>Frontend/.env</code>.
            </p>
          ) : null}
        </div>
      </article>

      <article id={polygonToolsBlock?.id ?? 'polygon-tools'} className="panel-card panel-card--my-farm-tools">
        <div className="panel-card__head">
          <h3>{polygonToolsBlock?.title ?? 'Polygon Drawing Tools'}</h3>
          <span className={`panel-status-badge panel-status-badge--${saveStatus}`}>{saveStatus}</span>
        </div>
        <p>{polygonToolsBlock?.description ?? 'Draw, update, and persist polygon boundaries.'}</p>

        <div className="panel-myfarm-grid">
          <div className="panel-myfarm-stat">
            <span>Field ID</span>
            <strong>{fieldId ?? 'Not saved yet'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>Polygon ID</span>
            <strong>{polygonId ?? 'Not saved yet'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>City</span>
            <strong>{polygonCity ?? 'Unknown'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>State</span>
            <strong>{polygonState ?? 'Unknown'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>Current location</span>
            <strong>
              {location ? `${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)}` : 'Not detected'}
            </strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>Current location ID</span>
            <strong>{currentLocationId}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>Boundary points</span>
            <strong>{Math.max(0, coordinateRing.length - 1)}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>Location status</span>
            <strong>{locationStatus}</strong>
          </div>
        </div>

        <p className="panel-myfarm-feedback">{saveMessage}</p>
        <p className="panel-myfarm-feedback panel-myfarm-feedback--muted">{locationMessage}</p>
      </article>

      <article id={ndviOverlayBlock?.id ?? 'ndvi-overlay'} className="panel-card panel-card--ndvi">
        <div className="panel-card__head">
          <h3>{ndviOverlayBlock?.title ?? 'NDVI Overlay'}</h3>
          <span className={`panel-status-badge panel-status-badge--${snapshotStatus}`}>{snapshotStatus}</span>
        </div>
        <p>{ndviOverlayBlock?.description ?? 'Visual preview zone for vegetation layers.'}</p>

        <div className="panel-myfarm-grid">
          <div className="panel-myfarm-stat">
            <span>Snapshot source</span>
            <strong>{snapshot?.source ?? 'N/A'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>Latest image date</span>
            <strong>{snapshot?.latest_image_date ?? 'N/A'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>NDVI mean</span>
            <strong>{snapshot?.ndvi_stats?.mean?.toFixed(3) ?? 'N/A'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>NDVI max</span>
            <strong>{snapshot?.ndvi_stats?.max?.toFixed(3) ?? 'N/A'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>Soil moisture</span>
            <strong>{snapshot?.soil?.soil_moisture ?? 'N/A'}</strong>
          </div>
          <div className="panel-myfarm-stat">
            <span>Air temp (°C)</span>
            <strong>{snapshot?.weather?.air_temp ?? 'N/A'}</strong>
          </div>
        </div>

        <p className="panel-myfarm-feedback">{snapshotMessage}</p>
        {snapshot?.ndvi_tile_url ? (
          <p className="panel-myfarm-feedback panel-myfarm-feedback--muted">
            NDVI tile URL linked and overlaid on map tile layer.
          </p>
        ) : null}
      </article>
    </div>
  )
}

export default MyFarmWorkspace
