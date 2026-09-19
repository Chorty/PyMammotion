"""Dataclass models for Mammotion direct-MQTT device properties payloads."""

from dataclasses import dataclass
from typing import Annotated

from mashumaro.config import BaseConfig
from mashumaro.mixins.orjson import DataClassORJSONMixin
from mashumaro.types import Alias


@dataclass
class FirmwareInfo(DataClassORJSONMixin):
    """Firmware component descriptor with type, component, and version fields."""

    t: str
    c: str
    v: str


@dataclass
class DeviceVersionInfo(DataClassORJSONMixin):
    """Overall device version and per-module firmware list."""

    dev_ver: Annotated[str, Alias("devVer")]
    whole: int
    fw_info: Annotated[list[FirmwareInfo], Alias("fwInfo")]

    class Config(BaseConfig):
        """Mashumaro config: accept both aliased and raw field names on deserialize."""

        allow_deserialization_not_by_alias = True


@dataclass
class Coordinate(DataClassORJSONMixin):
    """Geographic coordinate as longitude/latitude decimal degrees."""

    lon: float
    lat: float


@dataclass
class InternalNavigation(DataClassORJSONMixin):
    """Internal navigation subsystem bandwidth breakdown."""

    nav: Annotated[str, Alias("NAV")]
    pau: Annotated[str, Alias("Pau")]
    r_pau: Annotated[str, Alias("rPau")]
    mcu: Annotated[str, Alias("MCU")]
    app: Annotated[str, Alias("APP")]
    w_slp: Annotated[str, Alias("wSlp")]
    i_slp: Annotated[str, Alias("iSlp")]

    class Config(BaseConfig):
        """Mashumaro config: accept both aliased and raw field names on deserialize."""

        allow_deserialization_not_by_alias = True


@dataclass
class BandwidthTraffic(DataClassORJSONMixin):
    """Per-channel bandwidth traffic measurements for IoT, RoI, FPV, and internal navigation."""

    iot: Annotated[str, Alias("IoT")]
    roi: Annotated[str, Alias("RoI")]
    fpv: Annotated[str, Alias("FPV")]
    inav: InternalNavigation

    class Config(BaseConfig):
        """Mashumaro config: accept both aliased and raw field names on deserialize."""

        allow_deserialization_not_by_alias = True


@dataclass
class TrafficPeriod(DataClassORJSONMixin):
    """Network traffic statistics for a single time period (received, transmitted, speed)."""

    r: str
    t: str
    s: str


@dataclass
class TrafficData(DataClassORJSONMixin):
    """Aggregated traffic statistics grouped by hour, day, and month."""

    upt: str
    hour: Annotated[dict[str, TrafficPeriod], Alias("Hour")]
    day: Annotated[dict[str, TrafficPeriod], Alias("Day")]
    mon: Annotated[dict[str, TrafficPeriod], Alias("Mon")]

    class Config(BaseConfig):
        """Mashumaro config: accept both aliased and raw field names on deserialize."""

        allow_deserialization_not_by_alias = True


@dataclass
class NetworkInfo(DataClassORJSONMixin):
    """Comprehensive network information including WiFi, cellular, and traffic statistics."""

    ssid: str = ""
    wifi_sta_mac: str = ""
    wifi_rssi: int = 0
    bt_mac: str = ""
    mnet_model: str = ""
    imei: str = ""
    fw_ver: str = ""
    sim: str = ""
    imsi: str = ""
    mnet_rssi: int = 0
    signal: int = 0
    mnet_link: int = 0
    mnet_option: str = ""
    mnet_ip: str = ""
    apn_info: str = ""
    apn_cid: int = 0
    used_net: int = 0
    hub_reset: int = 0
    mnet_dis: int = 0
    airplane_times: int = 0
    lsusb_num: int = 0
    mnet_rx: str = ""
    mnet_tx: str = ""
    mnet_uniot: int = 0
    mnet_un_getiot: int = 0
    ssh_flag: str = ""
    mileage: str = ""
    work_time: str = ""
    bat_cycles: str = ""
    ip: str = ""
    apn_num: int = 0
    wifi_available: int = 0
    iccid: str = ""
    sim_source: str = ""
    mnet_reg: str = ""
    mnet_rsrp: str = ""
    mnet_snr: str = ""
    mnet_enable: int = 0
    wt_sec: int = 0
    b_tra: Annotated[BandwidthTraffic | None, Alias("bTra")] = None
    bw_tra: Annotated[BandwidthTraffic | None, Alias("bwTra")] = None
    m_tra: Annotated[TrafficData | None, Alias("mTra")] = None


@dataclass
class DeviceOtherInfo(DataClassORJSONMixin):
    """Miscellaneous diagnostic information reported in the ``deviceOtherInfo`` property.

    Every field is optional and defaults to ``None`` meaning "not reported in this
    post", so a device that omits a key (or a firmware that adds one later) does
    not raise ``MissingField`` and take the whole ``property/post`` down with it.
    ``None`` also lets :class:`MowerStateReducer` merge successive posts without a
    missing key clobbering a value an earlier post established.
    """

    soc_up_time: Annotated[int | None, Alias("socUpTime")] = None
    mcu_up_time: Annotated[int | None, Alias("mcuUpTime")] = None
    soc_loads: Annotated[str | None, Alias("socLoads")] = None
    soc_mem_free: Annotated[int | None, Alias("socMemFree")] = None
    soc_mem_total: Annotated[int | None, Alias("socMemTotal")] = None
    soc_mmc_life_time: Annotated[int | None, Alias("socMmcLifeTime")] = None
    usb_dis_cnt: Annotated[int | None, Alias("usbDisCnt")] = None
    soc_pstore: Annotated[int | None, Alias("socPstore")] = None
    soc_coredump: Annotated[int | None, Alias("socCoredump")] = None
    soc_tmp: Annotated[int | None, Alias("socTmp")] = None
    mc_mcu: Annotated[str | None, Alias("mcMcu")] = None
    i_msg_free: Annotated[int | None, Alias("iMsgFree")] = None
    i_msg_limit: Annotated[int | None, Alias("iMsgLimit")] = None
    i_msg_raw: Annotated[int | None, Alias("iMsgRaw")] = None
    i_msg_prop: Annotated[int | None, Alias("iMsgprop")] = None
    i_msg_serv: Annotated[int | None, Alias("iMsgServ")] = None
    i_msg_info: Annotated[int | None, Alias("iMsgInfo")] = None
    i_msg_warn: Annotated[int | None, Alias("iMsgWarn")] = None
    i_msg_fault: Annotated[int | None, Alias("iMsgFault")] = None
    i_msg_ota_stage: Annotated[int | None, Alias("iMsgOtaStage")] = None
    i_msg_protobuf: Annotated[int | None, Alias("iMsgProtobuf")] = None
    i_msg_notify: Annotated[int | None, Alias("iMsgNotify")] = None
    i_msg_log_prog: Annotated[int | None, Alias("iMsgLogProg")] = None
    i_msg_biz_req: Annotated[int | None, Alias("iMsgBizReq")] = None
    i_msg_cfg_req: Annotated[int | None, Alias("iMsgCfgReq")] = None
    i_msg_voice: Annotated[int | None, Alias("iMsgVoice")] = None
    i_msg_warn_code: Annotated[int | None, Alias("iMsgWarnCode")] = None
    pb_net: Annotated[int | None, Alias("pbNet")] = None
    pb_sys: Annotated[int | None, Alias("pbSys")] = None
    pb_nav: Annotated[int | None, Alias("pbNav")] = None
    pb_local: Annotated[int | None, Alias("pbLocal")] = None
    pb_plan: Annotated[int | None, Alias("pbPlan")] = None
    pb_e_drv: Annotated[int | None, Alias("pbEDrv")] = None
    pb_e_sys: Annotated[int | None, Alias("pbESys")] = None
    pb_midware: Annotated[int | None, Alias("pbMidware")] = None
    pb_ota: Annotated[int | None, Alias("pbOta")] = None
    pb_appl: Annotated[int | None, Alias("pbAppl")] = None
    pb_mul: Annotated[int | None, Alias("pbMul")] = None
    pb_other: Annotated[int | None, Alias("pbOther")] = None
    lora_connect: Annotated[int | None, Alias("loraConnect")] = None
    base_status: Annotated[int | None, Alias("Basestatus")] = None
    mqtt_rtk_switch: int | None = None
    mqtt_rtk_channel: int | None = None
    mqtt_rtk_status: int | None = None
    mqtt_rtcm_cnt: int | None = None
    mqtt_conn_cnt: int | None = None
    mqtt_disconn_cnt: int | None = None
    mqtt_rtk_hb_flag: int | None = None
    mqtt_rtk_hb_count: int | None = None
    mqtt_start_cnt: int | None = None
    mqtt_close_cnt: int | None = None
    mqtt_rtk_ssl_fail: int | None = None
    mqtt_rtk_wifi_config: int | None = None
    nrtk_svc_prov: int | None = None
    nrtk_svc_err: int | None = None
    base_stn_id: int | None = None
    rtk_status: int | None = None
    charge_status: int | None = None
    chassis_state: int | None = None
    nav: str | None = None
    ins_fusion: str | None = None
    perception: str | None = None
    vision_proxy: str | None = None
    vslam_vio: str | None = None
    iot_con_timeout: int | None = None
    iot_con: int | None = None
    iot_con_fail_max: str | None = None
    iot_con_fail_min: Annotated[str | None, Alias("iot_con_fail_min")] = None
    iot_url_count: int | None = None
    iot_url_max: str | None = None
    iot_url_min: str | None = None
    iot_cn: int | None = None
    iot_ap: int | None = None
    iot_us: int | None = None
    iot_eu: int | None = None
    task_area: float | None = None
    task_count: int | None = None
    task_hash: str | None = None
    systemio_boot_time: Annotated[str | None, Alias("systemioBootTime")] = None
    dds_no_gdc: int | None = None
    tilt_degree: str | None = None

    # --- Fields observed in real payloads that previously had no home. ---
    # Per-subsystem core-dump counters. The firmware's coredump_handler.sh writes
    # one core plus a .report sidecar per crash into /userdata/log/coredump, and
    # agl_monitor_process.sh restarts the failed service; these are the counts
    # that survive into the property post. soc_coredump above is the SoC total.
    embed_coredump: Annotated[int | None, Alias("embedCoredump")] = None
    nav_coredump: Annotated[int | None, Alias("navCoredump")] = None
    perception_coredump: Annotated[int | None, Alias("perceptionCoredump")] = None
    location_coredump: Annotated[int | None, Alias("locationCoredump")] = None
    other_coredump: Annotated[int | None, Alias("otherCoredump")] = None
    # agl_monitor_process.sh's boot-local /tmp/restart_count. -1 == not yet set.
    process_restart_count: int | None = None

    # Tilt, reported as decimal-degree strings alongside the existing tilt_degree.
    cur_tilt_degree: str | None = None
    max_work_tilt_degree: str | None = None

    # Network-RTK (NTRIP-style correction service) counters.
    nrtk_account_ready: int | None = None
    nrtk_freq: int | None = None
    nrtk_low_power: int | None = None
    nrtk_mountpoint: str | None = None
    nrtk_password_err: int | None = None
    nrtk_rate: int | None = None
    nrtk_req_cnt: int | None = None
    nrtk_req_flood: int | None = None
    nrtk_rtcm_bytes: int | None = None
    nrtk_rtcm_lose: int | None = None
    nrtk_traffic_limit: int | None = None
    nrtk_url: str | None = None

    # RTK transport selection and mobile-network/Wi-Fi switch counters.
    mqtt_net_choice: int | None = None
    rtk_mnet_to_wifi: int | None = None
    rtk_wifi_to_mnet: int | None = None

    # Map-switch error counters, keyed by the device's own error numbers.
    map_switch_err_101: int | None = None
    map_switch_err_102: int | None = None
    map_switch_err_103: int | None = None
    map_switch_err_104: int | None = None
    map_switch_err_105: int | None = None
    map_switch_err_106: int | None = None

    class Config(BaseConfig):
        """Mashumaro config: accept both aliased and raw field names on deserialize."""

        allow_deserialization_not_by_alias = True


@dataclass
class CheckData(DataClassORJSONMixin):
    """Self-test result with categorised error, warning, and OK code lists."""

    result: str
    error: Annotated[list[int], Alias("Error")]
    warn: Annotated[list[int], Alias("Warn")]
    ok: Annotated[list[int], Alias("OK")]

    class Config(BaseConfig):
        """Mashumaro config: accept both aliased and raw field names on deserialize."""

        allow_deserialization_not_by_alias = True


@dataclass
class DeviceProperties(DataClassORJSONMixin):
    """Full set of device properties received in a Mammotion direct-MQTT properties message.

    Every field is optional: devices send partial ``thing.event.property.post``
    messages carrying as few as one or two fields at a time, so any
    individual field may be absent from any given message.
    """

    # None (not 0) when the field is absent from this partial post, so consumers
    # can distinguish "not reported" from a genuine value of 0 (e.g. 0% battery,
    # or deviceState 0 == MODE_NOT_ACTIVE). Mirrors the nested-object fields below.
    device_state: Annotated[int | None, Alias("deviceState")] = None
    battery_percentage: Annotated[int | None, Alias("batteryPercentage")] = None
    device_version: Annotated[str, Alias("deviceVersion")] = ""
    knife_height: Annotated[int | None, Alias("knifeHeight")] = None
    lora_general_config: Annotated[str, Alias("loraGeneralConfig")] = ""
    ext_mod: Annotated[str, Alias("extMod")] = ""
    int_mod: Annotated[str, Alias("intMod")] = ""
    iot_state: Annotated[int, Alias("iotState")] = 0
    iot_msg_total: Annotated[int, Alias("iotMsgTotal")] = 0
    iot_msg_hz: Annotated[int, Alias("iotMsgHz")] = 0
    lt_mr_mod: Annotated[str, Alias("ltMrMod")] = ""
    rt_mr_mod: Annotated[str, Alias("rtMrMod")] = ""
    bms_hardware_version: Annotated[str, Alias("bmsHardwareVersion")] = ""
    stm32_h7_version: Annotated[str, Alias("stm32H7Version")] = ""
    mc_boot_version: Annotated[str, Alias("mcBootVersion")] = ""

    # Nested JSON objects — None when the device did not include the field
    # on this particular property/post.
    device_version_info: Annotated[DeviceVersionInfo | None, Alias("deviceVersionInfo")] = None
    coordinate: Coordinate | None = None
    device_other_info: Annotated[DeviceOtherInfo | None, Alias("deviceOtherInfo")] = None
    network_info: Annotated[NetworkInfo | None, Alias("networkInfo")] = None
    check_data: Annotated[CheckData | None, Alias("checkData")] = None
    iot_id: str = ""
    left_motor_version: Annotated[str, Alias("leftMotorVersion")] = ""
    right_motor_version: Annotated[str, Alias("rightMotorVersion")] = ""
    rtk_version: Annotated[str, Alias("rtkVersion")] = ""
    bms_version: Annotated[str, Alias("bmsVersion")] = ""
    left_motor_boot_version: Annotated[str, Alias("leftMotorBootVersion")] = ""
    right_motor_boot_version: Annotated[str, Alias("rightMotorBootVersion")] = ""

    class Config(BaseConfig):
        """Mashumaro config: accept raw field names and decode nested JSON-string fields."""

        allow_deserialization_not_by_alias = True
        serialization_strategy = {
            DeviceVersionInfo: {
                "deserialize": lambda x: DeviceVersionInfo.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
            Coordinate: {
                "deserialize": lambda x: Coordinate.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
            DeviceOtherInfo: {
                "deserialize": lambda x: DeviceOtherInfo.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
            NetworkInfo: {
                "deserialize": lambda x: NetworkInfo.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
            CheckData: {
                "deserialize": lambda x: CheckData.from_json(x) if isinstance(x, str) else x,
                "serialize": lambda x: x.to_json() if hasattr(x, "to_json") else x,
            },
        }
