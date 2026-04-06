package com.napominator.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.napominator.ui.main.MainScreen
import com.napominator.ui.onboarding.BatteryOnboardingScreen
import com.napominator.ui.settings.SettingsScreen
import com.napominator.ui.task.TaskDetailScreen

sealed class Screen(val route: String) {
    object Main : Screen("main")
    object BatteryOnboarding : Screen("battery_onboarding")
    object Settings : Screen("settings")
    object TaskDetail : Screen("task/{taskId}") {
        fun createRoute(taskId: Long) = "task/$taskId"
    }
    object NewTask : Screen("task/new")
}

@Composable
fun NavGraph(
    navController: NavHostController,
    startDestination: String = Screen.Main.route
) {
    NavHost(
        navController = navController,
        startDestination = startDestination
    ) {
        composable(Screen.Main.route) {
            MainScreen(
                onNavigateToTask = { taskId ->
                    navController.navigate(Screen.TaskDetail.createRoute(taskId))
                },
                onNavigateToSettings = {
                    navController.navigate(Screen.Settings.route)
                }
            )
        }

        composable(Screen.BatteryOnboarding.route) {
            BatteryOnboardingScreen(
                onDone = { navController.navigate(Screen.Main.route) {
                    popUpTo(Screen.BatteryOnboarding.route) { inclusive = true }
                }}
            )
        }

        composable(Screen.Settings.route) {
            SettingsScreen(
                onBack = { navController.popBackStack() }
            )
        }

        composable(
            route = Screen.TaskDetail.route,
            arguments = listOf(navArgument("taskId") { type = NavType.LongType })
        ) { backStackEntry ->
            val taskId = backStackEntry.arguments?.getLong("taskId") ?: return@composable
            TaskDetailScreen(
                taskId = taskId,
                onBack = { navController.popBackStack() }
            )
        }
    }
}
