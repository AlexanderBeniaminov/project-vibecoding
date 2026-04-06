package com.napominator.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

// Основные цвета (спокойная синяя палитра)
private val primaryLight = Color(0xFF1565C0)
private val onPrimaryLight = Color(0xFFFFFFFF)
private val primaryContainerLight = Color(0xFFD6E4FF)
private val backgroundLight = Color(0xFFF8F9FF)
private val surfaceLight = Color(0xFFFFFFFF)
private val errorLight = Color(0xFFBA1A1A)

private val primaryDark = Color(0xFF90B8FF)
private val onPrimaryDark = Color(0xFF00306B)
private val backgroundDark = Color(0xFF1A1C20)
private val surfaceDark = Color(0xFF1A1C20)

private val LightColorScheme = lightColorScheme(
    primary = primaryLight,
    onPrimary = onPrimaryLight,
    primaryContainer = primaryContainerLight,
    background = backgroundLight,
    surface = surfaceLight,
    error = errorLight,
)

private val DarkColorScheme = darkColorScheme(
    primary = primaryDark,
    onPrimary = onPrimaryDark,
    background = backgroundDark,
    surface = surfaceDark,
)

@Composable
fun NapominatorTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,  // Material You на Android 12+
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context)
            else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography(),
        content = content
    )
}
