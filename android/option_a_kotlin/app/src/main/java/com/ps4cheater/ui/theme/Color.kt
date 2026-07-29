package com.ps4cheater.ui.theme

import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color

// ---------------------------------------------------------------------------
// PS4-inspired dark theme colors
// ---------------------------------------------------------------------------

val Ps4Background = Color(0xFF0F0F0F)
val Ps4Surface = Color(0xFF1A1A1A)
val Ps4SurfaceVariant = Color(0xFF242424)
val Ps4Primary = Color(0xFF2196F3)
val Ps4OnPrimary = Color(0xFFFFFFFF)
val Ps4Secondary = Color(0xFF4FC3F7)
val Ps4OnSecondary = Color(0xFF000000)
val Ps4Error = Color(0xFFF44336)
val Ps4OnError = Color(0xFFFFFFFF)
val Ps4OnBackground = Color(0xFFE0E0E0)
val Ps4OnSurface = Color(0xFFE0E0E0)
val Ps4OnSurfaceVariant = Color(0xFFB0B0B0)
val Ps4Outline = Color(0xFF555555)

/**
 * darkColorScheme used by PS4CheaterTheme.
 * PS4 blue + dark surfaces, with red error state.
 */
val Ps4ColorScheme = darkColorScheme(
    primary = Ps4Primary,
    onPrimary = Ps4OnPrimary,
    primaryContainer = Ps4Primary,
    onPrimaryContainer = Ps4OnPrimary,
    secondary = Ps4Secondary,
    onSecondary = Ps4OnSecondary,
    secondaryContainer = Ps4Secondary,
    onSecondaryContainer = Ps4OnSecondary,
    tertiary = Ps4Secondary,
    onTertiary = Ps4OnSecondary,
    background = Ps4Background,
    onBackground = Ps4OnBackground,
    surface = Ps4Surface,
    onSurface = Ps4OnSurface,
    surfaceVariant = Ps4SurfaceVariant,
    onSurfaceVariant = Ps4OnSurfaceVariant,
    surfaceTint = Ps4Primary,
    error = Ps4Error,
    onError = Ps4OnError,
    errorContainer = Ps4Error,
    onErrorContainer = Ps4OnError,
    outline = Ps4Outline,
    outlineVariant = Ps4Outline,
    scrim = Color(0xFF000000),
)
