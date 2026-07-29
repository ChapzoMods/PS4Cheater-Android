package com.ps4cheater.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable

/**
 * PS4CheaterTheme — Material 3 theme for the PS4Cheater app.
 *
 * The app uses a fixed PS4-inspired dark color scheme (no dynamic color)
 * so the look is consistent across Android versions.
 *
 * @param dynamicColor ignored — kept for API compatibility. Always treated as false.
 * @param content composable content to render with the theme applied.
 */
@Composable
fun PS4CheaterTheme(
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit,
) {
    @Suppress("UNUSED_PARAMETER")
    val unused = dynamicColor // kept for API stability, intentionally not used.

    MaterialTheme(
        colorScheme = Ps4ColorScheme,
        typography = Ps4Typography,
        content = content,
    )
}
