import { LocateFixed, Save, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import MapboxDraw from '@mapbox/mapbox-gl-draw'
import '@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { PanelItem } from './panelConfig'
import { apiClient } from '../../services/apiClient'
import { getLocalizedApiError } from '../../services/apiErrors'
import { useLanguage } from '../../context/LanguageContext'
import { useSession } from '../../context/SessionContext'
import { useToast } from '../../context/ToastContext'
import type { AgroSnapshotResponse, DistrictItem } from '../../types/api'

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

const DEFAULT_CENTER: [number, number] = [76.7794, 30.7333]
const DEFAULT_ZOOM = 12
const MAPBOX_STYLE = 'mapbox://styles/mapbox/satellite-streets-v12'
const NDVI_SOURCE_ID = 'ks-ndvi-overlay-source'
const NDVI_LAYER_ID = 'ks-ndvi-overlay-layer'
const GOOGLE_USER_STORAGE_KEY = 'ks_google_user'

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

const getStoredGoogleUser = () => {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(GOOGLE_USER_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as { sub?: string; email?: string; name?: string; picture?: string; email_verified?: boolean }
  } catch {
    return null
  }
}

const MyFarmWorkspace = ({ item }: { item: PanelItem }) => {
  const { content } = useLanguage()
  const { pushToast } = useToast()
  const { farmerId, fieldId: storedFieldId, setFarmerId, setFieldId: storeFieldId } = useSession()
  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const drawRef = useRef<MapboxDraw | null>(null)
  const polygonBoundsRef = useRef<[[number, number], [number, number]] | null>(null)

  const [fieldId, setFieldId] = useState<string | null>(storedFieldId || null)
  const [fieldName, setFieldName] = useState('My Field')
  const [areaHectares, setAreaHectares] = useState('')

  const [polygonCoordinates, setPolygonCoordinates] = useState<Coordinates | null>(null)
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

  const [districts, setDistricts] = useState<DistrictItem[]>([])
  const [districtsLoading, setDistrictsLoading] = useState(false)
  const [districtError, setDistrictError] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [stateName, setStateName] = useState('')
  const [districtName, setDistrictName] = useState('')
  const [farmerStatus, setFarmerStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [farmerMessage, setFarmerMessage] = useState('')

  const mapboxToken = (import.meta.env.VITE_MAPBOX_TOKEN as string | undefined) ?? 'pk.DUMMY_MAPBOX_TOKEN_REPLACE_ME'
  const usingDummyToken = mapboxToken.includes('DUMMY') || mapboxToken.includes('dummy')

  const mapBlock = item.blocks.find((block) => block.id === 'mapbox-canvas')
  const polygonToolsBlock = item.blocks.find((block) => block.id === 'polygon-tools')
  const ndviOverlayBlock = item.blocks.find((block) => block.id === 'ndvi-overlay')

  const coordinateRing = useMemo(() => polygonCoordinates?.[0] ?? [], [polygonCoordinates])
  const currentLocationId = useMemo(
    () => (location ? toLocationId(location.latitude, location.longitude) : 'N/A'),
    [location],
  )

  const googleUser = useMemo(() => getStoredGoogleUser(), [])

  const states = useMemo(() => {
    const unique = new Set(districts.map((item) => item.state_name))
    return Array.from(unique).sort((a, b) => a.localeCompare(b))
  }, [districts])

  const districtsForState = useMemo(() => {
    return districts
      .filter((item) => item.state_name === stateName)
      .map((item) => item.dist_name)
      .sort((a, b) => a.localeCompare(b))
  }, [districts, stateName])

  useEffect(() => {
    if (!googleUser?.name) return
    setFullName((prev) => prev || googleUser.name || '')
  }, [googleUser])

  useEffect(() => {
    if (farmerId) {
      setFarmerStatus('saved')
      setFarmerMessage('Farmer profile active.')
    }
  }, [farmerId])

  useEffect(() => {
    if (farmerId) return
    let isActive = true
    const loadDistricts = async () => {
      setDistrictsLoading(true)
      setDistrictError('')
      try {
        const payload = await apiClient.getDistricts()
        if (!isActive) return
        setDistricts(payload)
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!isActive) return
        setDistrictError(message)
        pushToast(message, 'error')
      } finally {
        if (isActive) setDistrictsLoading(false)
      }
    }

    loadDistricts()
    return () => {
      isActive = false
    }
  }, [content, farmerId, pushToast])

  const handleRegisterFarmer = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault()

      if (!googleUser?.sub) {
        const message = content.errors.unauthorized
        setFarmerStatus('error')
        setFarmerMessage(message)
        pushToast(message, 'error')
        return
      }

      if (!fullName.trim() || !phone.trim() || !stateName || !districtName) {
        const message = content.errors.validation
        setFarmerStatus('error')
        setFarmerMessage(message)
        return
      }

      setFarmerStatus('saving')
      setFarmerMessage('Saving farmer profile...')

      try {
        const payload = await apiClient.registerFarmer({
          google_sub: googleUser.sub,
          name: fullName.trim(),
          phone: phone.trim(),
          state_name: stateName,
          dist_name: districtName,
          email: googleUser.email ?? undefined,
          email_verified: googleUser.email_verified ?? undefined,
          picture: googleUser.picture ?? undefined,
        })
        setFarmerId(payload.farmer_id)
        setFarmerStatus('saved')
        setFarmerMessage('Farmer profile saved. You can now register your field.')
        pushToast('Farmer profile created.', 'success')
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        setFarmerStatus('error')
        setFarmerMessage(message)
        pushToast(message, 'error')
      }
    },
    [content, districtName, fullName, googleUser, phone, pushToast, setFarmerId, stateName],
  )

  useEffect(() => {
    if (storedFieldId && storedFieldId !== fieldId) {
      setFieldId(storedFieldId)
    }
  }, [fieldId, storedFieldId])

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
        const payload = await apiClient.getAgroSnapshot(savedFieldId, start, end)
        setSnapshot(payload)
        setSnapshotStatus('loaded')
        setSnapshotMessage(
          payload.ndvi_tile_url
            ? 'NDVI tile overlay applied on map.'
            : 'Snapshot loaded, but NDVI tile URL is unavailable for this time window.',
        )

        updateNdviOverlayOnMap(payload.ndvi_tile_url)
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        setSnapshotStatus('error')
        setSnapshotMessage(message)
        pushToast(message, 'error')

        if (error && typeof error === 'object' && 'status' in error) {
          const status = (error as { status?: number }).status
          if (status === 404) {
            const fallback = localMockSnapshot(savedFieldId, savedPolygonId, start, end)
            setSnapshot(fallback)
            setSnapshotStatus('loaded')
            setSnapshotMessage('Live snapshot unavailable. Showing local mock NDVI metrics.')
          }
        }
        updateNdviOverlayOnMap(null)
      }
    },
    [content, pushToast, updateNdviOverlayOnMap],
  )

  const savePolygonToBackend = useCallback(
    async (coordinates: Coordinates) => {
      const normalizedFarmerId = farmerId.trim()
      if (!normalizedFarmerId) {
        const message = content.errors.validation
        setSaveStatus('error')
        setSaveMessage(message)
        pushToast(message, 'error')
        return
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
        const payload = await apiClient.registerFarm({
          farmer_id: normalizedFarmerId,
          field_name: fieldName.trim() || 'My Field',
          coordinates: ensureClosedRing(ring),
          area_hectares: parsedArea,
        })
        setFieldId(payload.field_id)
        storeFieldId(payload.field_id)
        setPolygonId(payload.polygon_id)
        setPolygonCity(payload.city_name ?? null)
        setPolygonState(payload.state_name ?? null)
        setSaveStatus('saved')
        setSaveMessage(`Boundary saved. Field ${payload.field_id}, Polygon ${payload.polygon_id}.`)

        await fetchAgroSnapshot(payload.field_id, payload.polygon_id)
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        setSaveStatus('error')
        setSaveMessage(message)
        pushToast(message, 'error')
      }
    },
    [areaHectares, content, farmerId, fieldName, fetchAgroSnapshot, pushToast, storeFieldId],
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
      <article className="panel-card panel-card--farmer">
        <div className="panel-card__head">
          <h3>Farmer Profile</h3>
          <span className={`panel-status-badge panel-status-badge--${farmerStatus}`}>{farmerStatus}</span>
        </div>
        <p>Register your farmer profile before drawing the field boundary.</p>

        {farmerId ? (
          <div className="panel-myfarm-grid">
            <div className="panel-myfarm-stat">
              <span>Farmer ID</span>
              <strong>{farmerId}</strong>
            </div>
            <div className="panel-myfarm-stat">
              <span>Status</span>
              <strong>Active</strong>
            </div>
          </div>
        ) : (
          <form className="panel-farmer-form" onSubmit={handleRegisterFarmer}>
            <label className="panel-myfarm-field">
              Full name
              <input
                type="text"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Ramesh Kumar"
                required
              />
            </label>
            <label className="panel-myfarm-field">
              Phone number
              <input
                type="tel"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                placeholder="9876543210"
                required
              />
            </label>
            <label className="panel-myfarm-field">
              State
              <select
                value={stateName}
                onChange={(event) => {
                  setStateName(event.target.value)
                  setDistrictName('')
                }}
                disabled={districtsLoading}
                required
              >
                <option value="">Select state</option>
                {states.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
            </label>
            <label className="panel-myfarm-field">
              District
              <select
                value={districtName}
                onChange={(event) => setDistrictName(event.target.value)}
                disabled={!stateName || districtsLoading}
                required
              >
                <option value="">Select district</option>
                {districtsForState.map((district) => (
                  <option key={district} value={district}>
                    {district}
                  </option>
                ))}
              </select>
            </label>
            <div className="panel-farmer-actions">
              <button type="submit" className="panel-mapbox__button" disabled={farmerStatus === 'saving'}>
                {farmerStatus === 'saving' ? 'Saving...' : 'Create farmer profile'}
              </button>
            </div>
          </form>
        )}

        {districtsLoading ? <p className="panel-myfarm-feedback">Loading districts…</p> : null}
        {districtError ? <p className="panel-myfarm-feedback panel-myfarm-feedback--muted">{districtError}</p> : null}
        {farmerMessage ? <p className="panel-myfarm-feedback">{farmerMessage}</p> : null}
      </article>

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
              onChange={(event) => setFarmerId(event.target.value)}
              placeholder="Paste farmer_id from /farmers/register"
              readOnly={Boolean(farmerId)}
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
          Tip: complete farmer registration first, then save your field boundary.
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
