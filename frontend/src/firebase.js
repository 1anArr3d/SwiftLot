import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyB7uKw99tngL0sSGktDRJqYXVVtqu4bAf4",
  authDomain: "swiftlot.firebaseapp.com",
  projectId: "swiftlot",
  storageBucket: "swiftlot.firebasestorage.app",
  messagingSenderId: "436916189180",
  appId: "1:436916189180:web:36ee953abf07405d4be479",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
