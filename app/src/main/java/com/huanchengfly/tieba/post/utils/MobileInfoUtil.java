package com.huanchengfly.tieba.post.utils;

import android.Manifest;
import android.annotation.SuppressLint;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.telephony.TelephonyManager;

import androidx.core.content.ContextCompat;

public class MobileInfoUtil {
    public static final String DEFAULT_IMEI = "000000000000000";

    // The SDK 29 annotation requires a privileged permission even for this
    // pre-Q compatibility path. Q+ never reaches telephony, and legacy reads
    // require READ_PHONE_STATE below. Do not add privileged manifest permissions.
    @SuppressLint({"HardwareIds", "MissingPermission"})
    public static String getIMEI(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q || context == null) {
            return DEFAULT_IMEI;
        }
        try {
            boolean granted = ContextCompat.checkSelfPermission(context, Manifest.permission.READ_PHONE_STATE)
                    == PackageManager.PERMISSION_GRANTED;
            return readLegacyDeviceId(Build.VERSION.SDK_INT, granted, () -> {
                TelephonyManager manager = (TelephonyManager) context.getSystemService(Context.TELEPHONY_SERVICE);
                return manager == null ? null : manager.getDeviceId();
            });
        } catch (Exception e) {
            return DEFAULT_IMEI;
        }
    }

    interface DeviceIdSource {
        String read();
    }

    // Keep the privacy boundary testable without reading a real hardware ID.
    static String readLegacyDeviceId(int apiLevel, boolean phonePermissionGranted, DeviceIdSource source) {
        if (apiLevel >= Build.VERSION_CODES.Q || !phonePermissionGranted) {
            return DEFAULT_IMEI;
        }
        try {
            String deviceId = source.read();
            return deviceId == null ? DEFAULT_IMEI : deviceId;
        } catch (Exception e) {
            // Includes permission revocation between the permission check and read.
            return DEFAULT_IMEI;
        }
    }
}
