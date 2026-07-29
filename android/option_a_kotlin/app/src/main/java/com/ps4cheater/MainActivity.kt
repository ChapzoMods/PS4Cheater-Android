package com.ps4cheater

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.ps4cheater.ui.navigation.PS4CheaterNavHost
import com.ps4cheater.ui.theme.PS4CheaterTheme

/**
 * MainActivity — punto de entrada de la app Android.
 *
 * Configura Compose con el tema de la app y lanza el NavHost que
 * gestiona la navegación entre las 5 pantallas:
 *   - Connect
 *   - ProcessList
 *   - Scanner
 *   - HexEditor
 *   - CheatTable
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PS4CheaterTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    PS4CheaterNavHost()
                }
            }
        }
    }
}
