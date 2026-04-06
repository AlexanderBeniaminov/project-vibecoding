package com.napominator

import android.os.Bundle
import android.os.PowerManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.*
import androidx.navigation.compose.rememberNavController
import com.napominator.ui.navigation.NavGraph
import com.napominator.ui.navigation.Screen
import com.napominator.ui.theme.NapominatorTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            NapominatorTheme {
                val navController = rememberNavController()

                // При первом запуске проверяем настройки батареи
                val startDestination = remember {
                    val pm = getSystemService(PowerManager::class.java)
                    val isIgnoring = pm?.isIgnoringBatteryOptimizations(packageName) == true
                    if (isIgnoring) Screen.Main.route else Screen.BatteryOnboarding.route
                }

                NavGraph(
                    navController = navController,
                    startDestination = startDestination
                )
            }
        }
    }
}
