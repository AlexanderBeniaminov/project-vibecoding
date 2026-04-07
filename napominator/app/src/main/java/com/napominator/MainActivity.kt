package com.napominator

import android.os.Bundle
import android.os.PowerManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.*
import androidx.lifecycle.lifecycleScope
import androidx.navigation.compose.rememberNavController
import com.napominator.alarm.DailySummaryScheduler
import com.napominator.ui.navigation.NavGraph
import com.napominator.ui.navigation.Screen
import com.napominator.ui.theme.NapominatorTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var dailySummaryScheduler: DailySummaryScheduler

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Планируем сводку дня при каждом запуске (idempotent — AlarmManager перезапишет)
        lifecycleScope.launch { dailySummaryScheduler.scheduleNext() }

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
