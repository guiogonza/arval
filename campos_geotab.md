# Campos que llegan de Geotab API

> Generado: 10 de febrero de 2026  
> Base de datos Geotab: 97 dispositivos (GO9)

---

## 1. Device (Dispositivos)

**74 campos por dispositivo**

### Campos que usamos actualmente

| Campo | Tipo | Ejemplo | Uso en el código |
|---|---|---|---|
| `id` | str | `b1777` | Identificador único del dispositivo |
| `name` | str | `PWQ809` | Se usa como "placa" en la BD |
| `serialNumber` | str | `G9EA2YH8T9AN` | IMEI / Serial del GPS |
| `deviceType` | str | `GO9` | Tipo de dispositivo |

### Campos disponibles que NO usamos (útiles)

| Campo | Tipo | Ejemplo | Para qué sirve |
|---|---|---|---|
| `licensePlate` | str | `PWQ809` | Placa real del vehículo (puede diferir de `name`) |
| `vehicleIdentificationNumber` | str | `8ANBD33F4TL295733` | VIN del vehículo |
| `engineVehicleIdentificationNumber` | str | `8ANBD33F4TL295733` | VIN leído del motor |
| `groups` | list | `[{id: 'GroupVehicleId'}, {id: 'b2B3A'}]` | Grupos/flotas asignados |
| `activeFrom` | datetime | `2026-01-23T14:02:37` | Fecha de activación |
| `activeTo` | datetime | `2050-01-01T00:00:00` | Fecha de desactivación |
| `timeZoneId` | str | `America/Bogota` | Zona horaria configurada |
| `devicePlans` | list | `['Pro']` | Plan contratado |
| `fuelTankCapacity` | int | `0` | Capacidad del tanque (si se configura) |
| `engineHourOffset` | int | `0` | Offset de horas motor |
| `comment` | str | `""` | Comentario del vehículo |
| `odometerOffset` | int | `0` | Offset del odómetro |
| `speedingOn` | int | `100` | Umbral de exceso activado (km/h) |
| `speedingOff` | int | `90` | Umbral de exceso desactivado (km/h) |
| `idleMinutes` | int | `3` | Minutos para considerar ralentí |
| `productId` | int | `120` | ID del producto Geotab |
| `major` / `minor` | int | `45` / `27` | Versión de firmware |

### Campos restantes (configuración avanzada)

| Campo | Tipo | Descripción |
|---|---|---|
| `accelerationWarningThreshold` | int | Umbral aceleración brusca |
| `brakingWarningThreshold` | int | Umbral frenado brusco |
| `corneringWarningThreshold` | int | Umbral giro brusco |
| `disableBuzzer` | bool | Buzzer deshabilitado |
| `enableBeepOnDangerousDriving` | bool | Beep en conducción peligrosa |
| `enableBeepOnIdle` | bool | Beep en ralentí |
| `enableBeepOnRpm` | bool | Beep en RPM alto |
| `enableSpeedWarning` | bool | Alerta de velocidad |
| `enableControlExternalRelay` | bool | Control de relay externo |
| `immobilizeUnit` | bool | Inmovilizar unidad |
| `immobilizeArming` | int | Tiempo armado inmovilización |
| `isActiveTrackingEnabled` | bool | Tracking activo |
| `forceActiveTracking` | bool | Forzar tracking activo |
| `isDriverSeatbeltWarningOn` | bool | Alerta cinturón conductor |
| `isPassengerSeatbeltWarningOn` | bool | Alerta cinturón pasajero |
| `isReverseDetectOn` | bool | Detección de reversa |
| `isIoxConnectionEnabled` | bool | Conexión IOX habilitada |
| `isContinuousConnectEnabled` | bool | Conexión continua |
| `rpmValue` | int | Umbral RPM |
| `seatbeltWarningSpeed` | int | Velocidad para alerta cinturón |
| `minAccidentSpeed` | int | Velocidad mínima para accidente |
| `maxSecondsBetweenLogs` | int | Máx segundos entre registros |
| `gpsOffDelay` | int | Delay apagado GPS |
| `enableMustReprogram` | bool | Requiere reprogramación |
| `ensureHotStart` | bool | Asegurar hot start |
| `pinDevice` | bool | Dispositivo fijo |
| `odometerFactor` | int | Factor odómetro |
| `auxWarningSpeed` | list | Velocidades de alerta auxiliar |
| `enableAuxWarning` | list | Alertas auxiliares habilitadas |
| `isAuxIgnTrigger` | list | Trigger ignición auxiliar |
| `isAuxInverted` | list | Auxiliares invertidos |
| `customParameters` | list | Parámetros personalizados |
| `customProperties` | list | Propiedades personalizadas |
| `deviceFlags` | dict | Características habilitadas |
| `devicePlanBillingInfo` | list | Info de facturación |
| `wifiHotspotLimits` | list | Límites WiFi hotspot |
| `mediaFiles` | list | Archivos multimedia |
| `autoGroups` | list | Grupos automáticos |
| `protobufCustomParameters` | list | Parámetros protobuf |
| `obdAlertEnabled` | bool | Alertas OBD |
| `engineType` | str | Tipo de motor |
| `goTalkLanguage` | str | Idioma GoTalk |
| `licenseState` | str | Estado de licencia |
| `listenOnlyModeReason` | str | Razón modo escucha |
| `ignoreDownloadsUntil` | datetime | Ignorar descargas hasta |
| `timeToDownload` | str | Tiempo para descarga |
| `workTime` | str | Horario laboral |
| `parameterVersion` | int | Versión de parámetros |
| `parameterVersionOnDevice` | int | Versión en dispositivo |
| `externalDeviceShutDownDelay` | int | Delay apagado dispositivo externo |
| `isSpeedIndicator` | bool | Indicador de velocidad |
| `accelerometerThresholdWarningFactor` | int | Factor umbral acelerómetro |

---

## 2. DeviceStatusInfo (Estado actual de vehículos)

**13 campos por registro**

### Campos que usamos

| Campo | Tipo | Ejemplo | Uso en el código |
|---|---|---|---|
| `device` | dict | `{'id': 'b17A1'}` | Referencia al dispositivo (⚠️ solo trae `id`, NO `name`) |
| `latitude` | float | `7.12539911` | Latitud actual |
| `longitude` | float | `-73.126503` | Longitud actual |
| `speed` | int | `0` / `59` | Velocidad actual (km/h) |
| `bearing` | int | `97` | Dirección/rumbo (grados) |
| `dateTime` | datetime | `2026-02-10T20:59:10+00:00` | Fecha/hora del dato |
| `isDeviceCommunicating` | bool | `true` | Si el dispositivo está comunicando |

### Campos disponibles que NO usamos

| Campo | Tipo | Ejemplo | Para qué sirve |
|---|---|---|---|
| `isDriving` | bool | `true` / `false` | Si el vehículo está conduciendo **ahora mismo** |
| `currentStateDuration` | timedelta | `00:43:30` | Tiempo en el estado actual (conduciendo/detenido) |
| `driver` | str | `UnknownDriverId` | Conductor asignado |
| `groups` | list | `[{id: 'GroupVehicleId'}, ...]` | Grupos del vehículo |
| `isHistoricLastDriver` | bool | `false` | Si el último conductor es histórico |
| `exceptionEvents` | list | `[]` | Eventos de excepción activos |

### ⚠️ Problema detectado

El campo `device` en `DeviceStatusInfo` solo trae `{'id': 'b17A1'}` — **NO trae `name`**.  
El código en `sync_service.py` hace `device.get('name')` que siempre retorna `None` y cae al fallback `str(device_id)`.  
**Solución:** Hacer un JOIN con la tabla de dispositivos o precargar un diccionario `{id: placa}`.

---

## 3. Trip (Viajes)

**30 campos por viaje**

### Campos que usamos

| Campo | Tipo | Ejemplo | Uso en el código |
|---|---|---|---|
| `start` | datetime | `2026-02-10T15:16:18+00:00` | Hora de inicio del viaje |
| `stop` | datetime | `2026-02-10T15:20:55+00:00` | Hora de fin del viaje |
| `distance` | float | `0.030448053` | Distancia recorrida **(ya en km)** |
| `drivingDuration` | timedelta | `00:04:36.960000` | Duración conduciendo |
| `maximumSpeed` | int | `3` | Velocidad máxima del viaje (km/h) |

### Campos disponibles que NO usamos (útiles)

| Campo | Tipo | Ejemplo | Para qué sirve |
|---|---|---|---|
| `averageSpeed` | float | `0.396` | Velocidad promedio (km/h) |
| `idlingDuration` | timedelta | `00:09:44` | Tiempo en ralentí |
| `stopDuration` | timedelta | `00:09:44` | Duración de la parada posterior |
| `stopPoint` | dict | `{x: -73.158, y: 7.063}` | Coordenadas donde terminó (x=lng, y=lat) |
| `engineHours` | float | `35420.96` | Horas acumuladas del motor |
| `isSeatBeltOff` | bool | `false` | Si se condujo sin cinturón |
| `driver` | str | `UnknownDriverId` | Conductor del viaje |
| `device` | dict | `{'id': 'b1777'}` | Dispositivo del viaje |
| `id` | str | `b454957A7` | ID único del viaje |
| `nextTripStart` | datetime | `2026-02-10T15:30:39+00:00` | Inicio del siguiente viaje |

### Campos de horario laboral (after hours)

| Campo | Tipo | Ejemplo | Descripción |
|---|---|---|---|
| `afterHoursDistance` | int | `0` | Distancia fuera de horario laboral |
| `afterHoursDrivingDuration` | timedelta | `00:00:00` | Duración conducción fuera de horario |
| `afterHoursStart` | bool | `false` | Si el viaje inició fuera de horario |
| `afterHoursEnd` | bool | `false` | Si el viaje terminó fuera de horario |
| `afterHoursStopDuration` | timedelta | `00:00:00` | Duración parada fuera de horario |
| `workDistance` | float | `0.030` | Distancia en horario laboral |
| `workDrivingDuration` | timedelta | `00:04:36` | Duración conducción en horario laboral |
| `workStopDuration` | timedelta | `00:09:44` | Duración parada en horario laboral |

### Campos de rangos de velocidad

| Campo | Tipo | Descripción |
|---|---|---|
| `speedRange1` | int | Distancia en rango de velocidad 1 |
| `speedRange1Duration` | timedelta | Duración en rango 1 |
| `speedRange2` | int | Distancia en rango de velocidad 2 |
| `speedRange2Duration` | timedelta | Duración en rango 2 |
| `speedRange3` | int | Distancia en rango de velocidad 3 |
| `speedRange3Duration` | timedelta | Duración en rango 3 |

### ⚠️ Problema detectado

La distancia (`distance`) ya viene en **km** desde Geotab (ej: `0.030 km`).  
El código en `sync_service.py` la divide entre 1000: `distance = (trip.get('distance') or 0) / 1000`  
Esto genera valores incorrectos (ej: `0.00003 km` en vez de `0.030 km`).

---

## 4. LogRecord (Puntos GPS crudos)

**6 campos por registro** — Es la entidad más simple.

| Campo | Tipo | Ejemplo | Uso en el código |
|---|---|---|---|
| `latitude` | float | `7.06286478` | ✅ Usamos |
| `longitude` | float | `-73.1582718` | ✅ Usamos |
| `speed` | int | `0` | ✅ Usamos (km/h) |
| `dateTime` | datetime | `2026-02-10T00:08:04+00:00` | ✅ Usamos |
| `device` | dict | `{'id': 'b1777'}` | Referencia al dispositivo |
| `id` | str/None | `bC1ECAC47` | ID del registro (puede ser None) |

> **Nota:** LogRecord NO incluye altitud, heading, ni ignición. Para esos datos se necesita `StatusData`.

---

## 5. StatusData (Diagnóstico del motor)

**7 campos por registro** — No se usa actualmente en el proyecto.

| Campo | Tipo | Ejemplo | Descripción |
|---|---|---|---|
| `data` | int/float | `2`, `92` | Valor del diagnóstico |
| `dateTime` | datetime | `2026-02-10T00:07:00+00:00` | Fecha/hora de la lectura |
| `device` | dict | `{'id': 'b1777'}` | Dispositivo |
| `diagnostic` | dict | `{'id': 'aV90hCq8zakusGKE1UsfXrw'}` | ID del diagnóstico (odómetro, RPM, combustible, etc.) |
| `controller` | str | `ControllerNoneId` | Controlador de la ECU |
| `version` | str | `000000026c0b7270` | Versión del registro |
| `id` | str | `b26C0B7270` | ID único |

> Para usar StatusData hay que mapear los IDs de `diagnostic` a nombres legibles (ej: odómetro, RPM, voltaje batería, nivel combustible).

---

## Resumen de problemas encontrados

| # | Problema | Archivo | Línea | Impacto |
|---|---|---|---|---|
| 1 | `distance` ya viene en km, se divide entre 1000 de más | `sync_service.py` | ~162 | Distancias 1000x más pequeñas |
| 2 | `device.name` no existe en DeviceStatusInfo | `sync_service.py` | ~97 | Placa se guarda como ID interno |
| 3 | `stopPoint` tiene lat/lng fin pero se guardan como 0 | `sync_service.py` | ~178 | Se pierden coordenadas de fin |
| 4 | `averageSpeed`, `idlingDuration` disponibles pero no se usan | `sync_service.py` | — | Datos útiles desperdiciados |
