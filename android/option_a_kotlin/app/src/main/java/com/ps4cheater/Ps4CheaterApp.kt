package com.ps4cheater

import android.app.Application
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * Ps4CheaterApp — Application class.
 *
 * Inicializa el runtime de Python (Chaquopy) al arrancar la app.
 * Esto debe hacerse una sola vez, antes de cualquier llamada a Python.
 */
class Ps4CheaterApp : Application() {

    companion object {
        private const val TAG = "Ps4CheaterApp"
    }

    override fun onCreate() {
        super.onCreate()

        // Inicializar Chaquopy (Python)
        if (!Python.isStarted()) {
            try {
                Python.start(AndroidPlatform(this))
                Log.i(TAG, "Python runtime initialized")

                // Verificar que los módulos se carguen correctamente
                val py = Python.getInstance()
                val module = py.getModule("chaquopy_bridge")
                val result = module.callAttr("check_imports")
                val ok = (result as? com.chaquo.python.PyObject)?.asMap()?.get("ok")?.toString() == "True"
                if (ok) {
                    Log.i(TAG, "Python bridge imports OK")
                } else {
                    Log.e(TAG, "Python bridge imports failed: $result")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to initialize Python", e)
            }
        }
    }
}
