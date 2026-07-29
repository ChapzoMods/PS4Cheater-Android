package com.ps4cheater.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.ps4cheater.MainActivity
import com.ps4cheater.R
import com.ps4cheater.data.Ps4Repository
import com.ps4cheater.data.PythonBridge
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.cancel

/**
 * FreezeService — Foreground Service que mantiene los cheats frozen activos.
 *
 * Cada 100ms llama a `repository.applyFrozen()` para re-escribir los valores
 * de los cheats marcados como frozen.
 *
 * El servicio corre en background incluso cuando la app está minimizada,
 * gracias a ser un Foreground Service con notificación persistente.
 */
class FreezeService : Service() {

    companion object {
        private const val TAG = "FreezeService"
        private const val CHANNEL_ID = "ps4cheater_freeze"
        private const val NOTIFICATION_ID = 1
        private const val FREEZE_INTERVAL_MS = 100L

        const val ACTION_START = "com.ps4cheater.START_FREEZE"
        const val ACTION_STOP = "com.ps4cheater.STOP_FREEZE"

        fun start(context: Context) {
            val intent = Intent(context, FreezeService::class.java).apply {
                action = ACTION_START
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            val intent = Intent(context, FreezeService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var freezeJob: Job? = null
    private var repository: Ps4Repository? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        // Initialize repository with PythonBridge
        try {
            val bridge = PythonBridge()
            repository = Ps4Repository(bridge)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create repository", e)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startFreeze()
            ACTION_STOP -> {
                stopFreeze()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
            else -> startFreeze()
        }
        return START_STICKY
    }

    private fun startFreeze() {
        val notification = createNotification("Freeze loop activo")
        startForeground(NOTIFICATION_ID, notification)

        if (freezeJob?.isActive == true) return

        freezeJob = scope.launch {
            while (true) {
                try {
                    repository?.applyFrozen()
                } catch (e: Exception) {
                    Log.e(TAG, "Freeze iteration failed", e)
                }
                delay(FREEZE_INTERVAL_MS)
            }
        }
    }

    private fun stopFreeze() {
        freezeJob?.cancel()
        freezeJob = null
    }

    override fun onDestroy() {
        super.onDestroy()
        stopFreeze()
        scope.cancel()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ------------------------------------------------------------------
    // Notification
    // ------------------------------------------------------------------

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Freeze Loop",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Mantiene los cheats frozen activos en background"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun createNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("PS4Cheater")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }
}
