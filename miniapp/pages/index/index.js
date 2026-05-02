const API = "https://122.51.236.219:8000"
const app = getApp()

Page({
  data: { books: [] },

  onLoad() { if (app.globalData.token) this.loadBooks() },

  login() {
    app.wxLogin((err, d) => {
      if (!err) { wx.showToast({ title: "登录成功" }); this.loadBooks() }
      else wx.showToast({ title: "登录失败", icon: "none" })
    })
  },

  loadBooks() {
    wx.request({
      url: API + "/api/books",
      header: { Authorization: "Bearer " + app.globalData.token },
      success: r => this.setData({ books: r.data.items || [] })
    })
  },

  openBook(e) {
    wx.navigateTo({ url: "/pages/read/read?id=" + e.currentTarget.dataset.id })
  }
})
